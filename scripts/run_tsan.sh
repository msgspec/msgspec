#!/usr/bin/env bash
# Build msgspec with ThreadSanitizer inside nascheme/cpython-tsan and run tests/unit.
set -euxo pipefail
cd "$(dirname "$0")/.."

export PYTHON_GIL=0 MSGSPEC_TSAN=1
export CC="${CC:-clang-21}" CXX="${CXX:-clang++-21}"
export SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0+tsan
export MSGSPEC_STRESS=1
trap 'chown -R --reference=. . 2>/dev/null || true' EXIT
ulimit -c 0  # no core files

python -c "import sys; assert not sys._is_gil_enabled()"

SYMBOLIZER=$(command -v llvm-symbolizer-21 || command -v llvm-symbolizer || true)
if [[ -z "${SYMBOLIZER}" ]] || ! command -v "${CC}" > /dev/null; then
  echo "::error::CC='${CC}' or llvm-symbolizer not found"
  find /usr/bin -maxdepth 1 \( -name '*clang*' -o -name '*llvm*' \) || true
  exit 1
fi
"${CC}" --version

python -m pip install -q uv
PYTHON="$(command -v python)"
uv pip install -q --python "${PYTHON}" --break-system-packages \
  "setuptools>=80" "setuptools-scm>=8" --group test-unit
uv pip install -q --python "${PYTHON}" --break-system-packages --no-build-isolation -e .

nm -D src/msgspec/_core*.so > /tmp/nm.txt
grep -q __tsan /tmp/nm.txt
python -c "import msgspec, sys; assert not sys._is_gil_enabled(), 'import re-enabled the GIL'"

cat /work/tsan_suppressions/*.txt > /tmp/supp.txt
cat >> /tmp/supp.txt <<'EOF'
# CPython's own _decimal races, unrelated to msgspec
race:dec_addstatus
race:dec_hash
EOF
mkdir -p tsan-logs pytest-logs
rm -f tsan-logs/* pytest-logs/*

STRESS=tests/unit/test_free_threading.py
COMMON=(tests/unit --ignore=tests/unit/test_performance.py --ignore="${STRESS}")

# exitcode=66
tsan_opts() {
  echo "suppressions=/tmp/supp.txt:external_symbolizer_path=${SYMBOLIZER}:halt_on_error=0:exitcode=66:history_size=7:second_deadlock_stack=1:handle_segv=0:log_path=${PWD}/tsan-logs/${1}"
}


LAST_RC=0
run_phase() {  
  local phase=$1 opts
  shift
  opts="$(tsan_opts "${phase}")"
  LAST_RC=0
  TSAN_OPTIONS="${opts}" \
    timeout 2400 python -X faulthandler -m pytest "$@" -p no:randomly -q 2>&1 \
    | tee "pytest-logs/${phase}.txt" || LAST_RC=${PIPESTATUS[0]}
  echo "${phase}: pytest exit code ${LAST_RC}" >> pytest-logs/exit-codes.txt
}

symbolize_core_frames() {  # $1 = pytest log
  local so offsets addrs
  so=$(find src/msgspec -maxdepth 1 -name '_core*.so' | head -n 1)
  offsets=$({ grep -o '_core[^"]*\.so", at +0x[0-9a-f]*' "$1" | grep -o '0x[0-9a-f]*$' | awk '!seen[$0]++' | tr '\n' ' '; } || true)
  [[ -n "${offsets}" ]] || return 0
  read -r -a addrs <<< "${offsets}"
  "${SYMBOLIZER}" --obj="${so}" --inlining --demangle "${addrs[@]}" || true
}


# One test per process
isolate_stress() {
  local ids n=0 rc id opts
  mapfile -t ids < <(python -m pytest --collect-only -q -p no:randomly "${STRESS}" 2>/dev/null | grep '::' || true)
  : > pytest-logs/stress-isolated.txt
  for id in "${ids[@]}"; do
    n=$((n + 1)); rc=0
    opts="$(tsan_opts "stress-${n}")"
    TSAN_OPTIONS="${opts}" \
      timeout 900 python -X faulthandler -m pytest "${id}" -p no:randomly -q \
      > "pytest-logs/stress-${n}.txt" 2>&1 || rc=$?
    echo "${rc} ${id}" >> pytest-logs/stress-isolated.txt
  done
}

FAILED=0 
run_phase stress "${STRESS}"

[[ "${LAST_RC}" -eq 0 ]] || FAILED=1
if [[ "${LAST_RC}" -ge 124 ]]; then  # abort/segfault/timeout
  isolate_stress
fi
run_phase baseline "${COMMON[@]}"
[[ "${LAST_RC}" -eq 0 ]] || FAILED=1

shopt -s nullglob
logs=(tsan-logs/*)
{
  echo "## pytest exit codes per phase (0=ok, 1=test failures, 2=collection error, 66=TSAN reported or died, 124=timeout, 134=abort, 139=segfault)"
  cat pytest-logs/exit-codes.txt
  if [[ -s pytest-logs/stress-isolated.txt ]]; then
    echo
    echo "## stress tests rerun one per process (exit code, test); non-zero means it failed or crashed"
    grep -v '^0 ' pytest-logs/stress-isolated.txt || echo "(all passed in isolation)"
  fi
  echo
  echo "## TSAN unique race sites"
  if [[ ${#logs[@]} -eq 0 ]]; then
    echo "(none: no TSAN reports)"
  else
    grep -h "SUMMARY: ThreadSanitizer" "${logs[@]}" | sort | uniq -c | sort -rn || true
    echo
    echo "## Reports by first msgspec frame (_core.c)"
    awk 'BEGIN{RS="==================\n"}
         /WARNING: ThreadSanitizer/ {
           if (match($0, /[^ ]*_core\.c:[0-9]+/)) print substr($0, RSTART, RLENGTH)
           else print "(no _core.c frame)"
         }' "${logs[@]}" | sort | uniq -c | sort -rn
  fi
  for f in pytest-logs/stress*.txt; do
    if grep -q "Fatal Python error" "${f}"; then
      echo
      echo "## crash in ${f}: assertion text and Python stack"
      { grep -h "Assertion\|assert" "${f}" | head -5; grep -A8 "^Stack (most recent call first)" "${f}" | head -12; } || true
      echo "## msgspec frames in ${f} (function, file:line)"
      symbolize_core_frames "${f}"
    fi
  done
  for f in "${logs[@]}"; do
    if grep -q "ERROR: ThreadSanitizer\|CHECK failed" "${f}"; then
      echo
      echo "## fatal signal / TSAN failure in ${f} (first 60 lines)"
      head -60 "${f}"
    fi
  done
} | tee tsan-summary.txt | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"

status=0
[[ ${#logs[@]} -eq 0 ]] || ! grep -q "SUMMARY: ThreadSanitizer" "${logs[@]}" || status=1
[[ "${FAILED}" -eq 0 ]] || status=1
exit "${status}"
