#define JSON_CAT_I(a, b) a##b
#define JSON_CAT(a, b) JSON_CAT_I(a, b)
#define J(name) JSON_CAT(JSON_PREFIX, name)
#ifndef JSON_ALLOW_COMMENTS
#define JSON_ALLOW_COMMENTS 0
#endif

static MS_INLINE bool
J(_read1)(JSONDecoderState *self, unsigned char *c)
{
    if (MS_UNLIKELY(self->input_pos == self->input_end)) {
        ms_err_truncated();
        return false;
    }
    *c = *self->input_pos;
    self->input_pos += 1;
    return true;
}

static MS_INLINE char
J(_peek_or_null)(JSONDecoderState *self) {
    if (MS_UNLIKELY(self->input_pos == self->input_end)) return '\0';
    return *self->input_pos;
}

/* Consume a comment at the current input position.
 * Returns 1 when a comment was consumed, 0 when the current character is not
 * the start of a comment, and -1 for a truncated block comment. */
#if JSON_ALLOW_COMMENTS
static MS_NOINLINE int
J(_consume_comment)(JSONDecoderState *self)
{
    if (self->input_end - self->input_pos < 2) return 0;
    unsigned char c = self->input_pos[1];
    if (c == '/') {
        self->input_pos += 2;
        while (self->input_pos < self->input_end &&
               *self->input_pos != '\n' && *self->input_pos != '\r') {
            self->input_pos++;
        }
        return 1;
    }
    if (c == '*') {
        self->input_pos += 2;
        while (self->input_end - self->input_pos >= 2 &&
               !(self->input_pos[0] == '*' && self->input_pos[1] == '/')) {
            self->input_pos++;
        }
        if (MS_UNLIKELY(self->input_end - self->input_pos < 2)) {
            ms_err_truncated();
            return -1;
        }
        self->input_pos += 2;
        return 1;
    }
    return 0;
}
#endif

static MS_INLINE bool
J(_peek_skip_ws)(JSONDecoderState *self, unsigned char *s)
{
    while (true) {
        if (MS_UNLIKELY(self->input_pos == self->input_end)) {
            ms_err_truncated();
            return false;
        }
        unsigned char c = *self->input_pos;
        if (MS_LIKELY(c != ' ' && c != '\n' && c != '\r' && c != '\t')) {
#if JSON_ALLOW_COMMENTS
            if (MS_LIKELY(c != '/')) {
                *s = c;
                return true;
            }
            int status = J(_consume_comment)(self);
            if (status < 0) return false;
            if (status > 0) continue;
#else
            *s = c;
            return true;
#endif
        }
        self->input_pos++;
    }
}

static MS_INLINE bool
J(_remaining)(JSONDecoderState *self, ptrdiff_t remaining)
{
    return self->input_end - self->input_pos >= remaining;
}

static PyObject *
J(_err_invalid)(JSONDecoderState *self, const char *msg)
{
    PyErr_Format(
        msgspec_get_global_state()->DecodeError,
        "JSON is malformed: %s (byte %zd)",
        msg,
        (Py_ssize_t)(self->input_pos - self->input_start)
    );
    return NULL;
}

static MS_INLINE bool
J(_has_trailing_characters)(JSONDecoderState *self)
{
    while (self->input_pos != self->input_end) {
        unsigned char c = *self->input_pos++;
        if (c == ' ' || c == '\n' || c == '\t' || c == '\r') {
            continue;
        }
#if JSON_ALLOW_COMMENTS
        if (c == '/' && self->input_pos < self->input_end) {
            if (self->input_pos[0] == '/') {
                self->input_pos++;
                while (self->input_pos < self->input_end &&
                       *self->input_pos != '\n' && *self->input_pos != '\r') {
                    self->input_pos++;
                }
                continue;
            }
            if (self->input_pos[0] == '*') {
                self->input_pos++;
                while (self->input_end - self->input_pos >= 2 &&
                       !(self->input_pos[0] == '*' && self->input_pos[1] == '/')) {
                    self->input_pos++;
                }
                if (self->input_end - self->input_pos < 2) {
                    ms_err_truncated();
                    return true;
                }
                self->input_pos += 2;
                continue;
            }
        }
#endif
        J(_err_invalid)(self, "trailing characters");
        return true;
    }
    return false;
}

static int J(_skip)(JSONDecoderState *self);

static PyObject * J(_decode)(
    JSONDecoderState *self, TypeNode *type, PathNode *path
);

static PyObject *
J(_decode_none)(JSONDecoderState *self, TypeNode *type, PathNode *path) {
    self->input_pos++;  /* Already checked as 'n' */
    if (MS_UNLIKELY(!J(_remaining)(self, 3))) {
        ms_err_truncated();
        return NULL;
    }
    unsigned char c1 = *self->input_pos++;
    unsigned char c2 = *self->input_pos++;
    unsigned char c3 = *self->input_pos++;
    if (MS_UNLIKELY(c1 != 'u' || c2 != 'l' || c3 != 'l')) {
        return J(_err_invalid)(self, "invalid character");
    }
    if (type->types & (MS_TYPE_ANY | MS_TYPE_NONE)) {
        Py_INCREF(Py_None);
        return Py_None;
    }
    return ms_validation_error("null", type, path);
}

static PyObject *
J(_decode_true)(JSONDecoderState *self, TypeNode *type, PathNode *path) {
    self->input_pos++;  /* Already checked as 't' */
    if (MS_UNLIKELY(!J(_remaining)(self, 3))) {
        ms_err_truncated();
        return NULL;
    }
    unsigned char c1 = *self->input_pos++;
    unsigned char c2 = *self->input_pos++;
    unsigned char c3 = *self->input_pos++;
    if (MS_UNLIKELY(c1 != 'r' || c2 != 'u' || c3 != 'e')) {
        return J(_err_invalid)(self, "invalid character");
    }
    if (type->types & (MS_TYPE_ANY | MS_TYPE_BOOL | MS_TYPE_BOOLLITERAL_TRUE)) {
        Py_INCREF(Py_True);
        return Py_True;
    }
    if (type->types & MS_TYPE_BOOLLITERAL_FALSE) {
        ms_raise_validation_error(path, "Invalid enum value %R%U", Py_True);
        return NULL;
    }
    return ms_validation_error("bool", type, path);
}

static PyObject *
J(_decode_false)(JSONDecoderState *self, TypeNode *type, PathNode *path) {
    self->input_pos++;  /* Already checked as 'f' */
    if (MS_UNLIKELY(!J(_remaining)(self, 4))) {
        ms_err_truncated();
        return NULL;
    }
    unsigned char c1 = *self->input_pos++;
    unsigned char c2 = *self->input_pos++;
    unsigned char c3 = *self->input_pos++;
    unsigned char c4 = *self->input_pos++;
    if (MS_UNLIKELY(c1 != 'a' || c2 != 'l' || c3 != 's' || c4 != 'e')) {
        return J(_err_invalid)(self, "invalid character");
    }
    if (type->types & (MS_TYPE_ANY | MS_TYPE_BOOL | MS_TYPE_BOOLLITERAL_FALSE)) {
        Py_INCREF(Py_False);
        return Py_False;
    }
    if (type->types & MS_TYPE_BOOLLITERAL_TRUE) {
        ms_raise_validation_error(path, "Invalid enum value %R%U", Py_False);
        return NULL;
    }
    return ms_validation_error("bool", type, path);
}

#define JS_SCRATCH_MAX_SIZE 1024

static int
J(_scratch_resize)(JSONDecoderState *state, Py_ssize_t size) {
    unsigned char *temp = PyMem_Realloc(state->scratch, size);
    if (MS_UNLIKELY(temp == NULL)) {
        PyErr_NoMemory();
        return -1;
    }
    state->scratch = temp;
    state->scratch_capacity = size;
    return 0;
}

static MS_NOINLINE int
J(_scratch_expand)(JSONDecoderState *state, Py_ssize_t required) {
    size_t new_size = Py_MAX(8, 1.5 * required);
    return J(_scratch_resize)(state, new_size);
}

static int
J(_scratch_extend)(JSONDecoderState *state, const void *buf, Py_ssize_t size) {
    Py_ssize_t required = state->scratch_len + size;
    if (MS_UNLIKELY(required >= state->scratch_capacity)) {
        if (MS_UNLIKELY(J(_scratch_expand)(state, required) < 0)) return -1;
    }
    memcpy(state->scratch + state->scratch_len, buf, size);
    state->scratch_len += size;
    return 0;
}

#ifndef MSGSPEC_JSON_SHARED_CHAR_TABLES
#define MSGSPEC_JSON_SHARED_CHAR_TABLES
/* -1: '\', '"', and forbidden characters
 * 0: ascii
 * 1: non-ascii */
static const int8_t char_types[256] = {
    -1, -1, -1, -1, -1, -1, -1, -1,
    -1, -1, -1, -1, -1, -1, -1, -1,
    -1, -1, -1, -1, -1, -1, -1, -1,
    -1, -1, -1, -1, -1, -1, -1, -1,
    0, 0, -1, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, -1, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
};

/* Is char `"`, `\`, or nonascii? */
static MS_INLINE bool char_is_special_or_nonascii(unsigned char c) {
    return char_types[c] != 0;
}

/* Is char `"` or `\`? */
static MS_INLINE bool char_is_special(unsigned char c) {
    return char_types[c] < 0;
}
#endif

static int
J(_read_codepoint)(JSONDecoderState *self, unsigned int *out) {
    unsigned char c;
    unsigned int cp = 0;
    if (!J(_remaining)(self, 4)) return ms_err_truncated();
    for (int i = 0; i < 4; i++) {
        c = *self->input_pos++;
        if (c >= '0' && c <= '9') {
            c -= '0';
        }
        else if (c >= 'a' && c <= 'f') {
            c = c - 'a' + 10;
        }
        else if (c >= 'A' && c <= 'F') {
            c = c - 'A' + 10;
        }
        else {
            J(_err_invalid)(self, "invalid character in unicode escape");
            return -1;
        }
        cp = (cp << 4) + c;
    }
    *out = cp;
    return 0;
}

static MS_NOINLINE int
J(_handle_unicode_escape)(JSONDecoderState *self) {
    unsigned int cp;
    if (J(_read_codepoint)(self, &cp) < 0) return -1;

    if (0xDC00 <= cp && cp <= 0xDFFF) {
        J(_err_invalid)(self, "invalid utf-16 surrogate pair");
        return -1;
    }
    else if (0xD800 <= cp && cp <= 0xDBFF) {
        /* utf-16 pair, parse 2nd pair */
        unsigned int cp2;
        if (!J(_remaining)(self, 6)) return ms_err_truncated();
        if (self->input_pos[0] != '\\' || self->input_pos[1] != 'u') {
            J(_err_invalid)(self, "unexpected end of escaped utf-16 surrogate pair");
            return -1;
        }
        self->input_pos += 2;
        if (J(_read_codepoint)(self, &cp2) < 0) return -1;
        if (cp2 < 0xDC00 || cp2 > 0xDFFF) {
            J(_err_invalid)(self, "invalid utf-16 surrogate pair");
            return -1;
        }
        cp = 0x10000 + (((cp - 0xD800) << 10) | (cp2 - 0xDC00));
    }

    /* Encode the codepoint as utf-8 */
    unsigned char *p = self->scratch + self->scratch_len;
    if (cp < 0x80) {
        *p++ = cp;
        self->scratch_len += 1;
    } else if (cp < 0x800) {
        *p++ = 0xC0 | (cp >> 6);
        *p++ = 0x80 | (cp & 0x3F);
        self->scratch_len += 2;
    } else if (cp < 0x10000) {
        *p++ = 0xE0 | (cp >> 12);
        *p++ = 0x80 | ((cp >> 6) & 0x3F);
        *p++ = 0x80 | (cp & 0x3F);
        self->scratch_len += 3;
    } else {
        *p++ = 0xF0 | (cp >> 18);
        *p++ = 0x80 | ((cp >> 12) & 0x3F);
        *p++ = 0x80 | ((cp >> 6) & 0x3F);
        *p++ = 0x80 | (cp & 0x3F);
        self->scratch_len += 4;
    }
    return 0;
}

#define parse_ascii_pre(i) \
    if (MS_UNLIKELY(char_is_special_or_nonascii(self->input_pos[i]))) goto parse_ascii_##i;

#define parse_ascii_post(i) \
    parse_ascii_##i: \
    self->input_pos += i; \
    goto parse_ascii_end;

#define parse_unicode_pre(i) \
    if (MS_UNLIKELY(char_is_special(self->input_pos[i]))) goto parse_unicode_##i;

#define parse_unicode_post(i) \
    parse_unicode_##i: \
    self->input_pos += i; \
    goto parse_unicode_end;

static MS_NOINLINE Py_ssize_t
J(_decode_string_view_copy)(
    JSONDecoderState *self, char **out, bool *is_ascii, unsigned char *start
) {
    unsigned char c;
    self->scratch_len = 0;

top:
    OPT_FORCE_RELOAD(*self->input_pos);

    c = *self->input_pos;
    if (c == '\\') {
        /* Write the current block to scratch */
        Py_ssize_t block_size = self->input_pos - start;
        /* An escape string requires at most 4 bytes to decode */
        Py_ssize_t required = self->scratch_len + block_size + 4;
        if (MS_UNLIKELY(required >= self->scratch_capacity)) {
            if (MS_UNLIKELY(J(_scratch_expand)(self, required) < 0)) return -1;
        }
        memcpy(self->scratch + self->scratch_len, start, block_size);
        self->scratch_len += block_size;

        self->input_pos++;
        if (!J(_read1)(self, &c)) return -1;

        switch (c) {
            case 'n': {
                *(self->scratch + self->scratch_len) = '\n';
                self->scratch_len++;
                break;
            }
            case '"': {
                *(self->scratch + self->scratch_len) = '"';
                self->scratch_len++;
                break;
            }
            case 't': {
                *(self->scratch + self->scratch_len) = '\t';
                self->scratch_len++;
                break;
            }
            case 'r': {
                *(self->scratch + self->scratch_len) = '\r';
                self->scratch_len++;
                break;
            }
            case '\\': {
                *(self->scratch + self->scratch_len) = '\\';
                self->scratch_len++;
                break;
            }
            case '/': {
                *(self->scratch + self->scratch_len) = '/';
                self->scratch_len++;
                break;
            }
            case 'b': {
                *(self->scratch + self->scratch_len) = '\b';
                self->scratch_len++;
                break;
            }
            case 'f': {
                *(self->scratch + self->scratch_len) = '\f';
                self->scratch_len++;
                break;
            }
            case 'u': {
                *is_ascii = false;
                if (J(_handle_unicode_escape)(self) < 0) return -1;
                break;
            }
            default:
                J(_err_invalid)(self, "invalid escape character in string");
                return -1;
        }

        start = self->input_pos;
    }
    else if (c == '"') {
        if (J(_scratch_extend)(self, start, self->input_pos - start) < 0) return -1;
        self->input_pos++;
        *out = (char *)(self->scratch);
        return self->scratch_len;
    }
    else {
        J(_err_invalid)(self, "invalid character");
        return -1;
    }

    /* Loop until `"`, `\`, or a non-ascii character */
    while (self->input_end - self->input_pos >= 8) {
        repeat8(parse_ascii_pre);
        self->input_pos += 8;
        continue;
        repeat8(parse_ascii_post);
    }
    while (true) {
        if (MS_UNLIKELY(self->input_pos == self->input_end)) return ms_err_truncated();
        if (MS_UNLIKELY(char_is_special_or_nonascii(*self->input_pos))) break;
        self->input_pos++;
    }

parse_ascii_end:
    OPT_FORCE_RELOAD(*self->input_pos);

    if (MS_UNLIKELY(*self->input_pos & 0x80)) {
        *is_ascii = false;
        /* Loop until `"` or `\` */
        while (self->input_end - self->input_pos >= 8) {
            repeat8(parse_unicode_pre);
            self->input_pos += 8;
            continue;
            repeat8(parse_unicode_post);
        }
        while (true) {
            if (MS_UNLIKELY(self->input_pos == self->input_end)) return ms_err_truncated();
            if (MS_UNLIKELY(char_is_special(*self->input_pos))) break;
            self->input_pos++;
        }
    }
parse_unicode_end:
    goto top;
}

static Py_ssize_t
J(_decode_string_view)(JSONDecoderState *self, char **out, bool *is_ascii) {
    self->input_pos++; /* Skip '"' */
    unsigned char *start = self->input_pos;

    /* Loop until `"`, `\`, or a non-ascii character */
    while (self->input_end - self->input_pos >= 8) {
        repeat8(parse_ascii_pre);
        self->input_pos += 8;
        continue;
        repeat8(parse_ascii_post);
    }
    while (true) {
        if (MS_UNLIKELY(self->input_pos == self->input_end)) return ms_err_truncated();
        if (MS_UNLIKELY(char_is_special_or_nonascii(*self->input_pos))) break;
        self->input_pos++;
    }

parse_ascii_end:
    OPT_FORCE_RELOAD(*self->input_pos);

    if (MS_LIKELY(*self->input_pos == '"')) {
        Py_ssize_t size = self->input_pos - start;
        self->input_pos++;
        *out = (char *)start;
        return size;
    }

    if (MS_UNLIKELY(*self->input_pos & 0x80)) {
        *is_ascii = false;
        /* Loop until `"` or `\` */
        while (self->input_end - self->input_pos >= 8) {
            repeat8(parse_unicode_pre);
            self->input_pos += 8;
            continue;
            repeat8(parse_unicode_post);
        }
        while (true) {
            if (MS_UNLIKELY(self->input_pos == self->input_end)) return ms_err_truncated();
            if (MS_UNLIKELY(char_is_special(*self->input_pos))) break;
            self->input_pos++;
        }
    }

parse_unicode_end:
    OPT_FORCE_RELOAD(*self->input_pos);

    if (MS_LIKELY(*self->input_pos == '"')) {
        Py_ssize_t size = self->input_pos - start;
        self->input_pos++;
        *out = (char *)start;
        return size;
    }

    return J(_decode_string_view_copy)(self, out, is_ascii, start);
}

static int
J(_skip_string)(JSONDecoderState *self) {
    self->input_pos++; /* Skip '"' */

parse_unicode:
    /* Loop until `"` or `\` */
    while (self->input_end - self->input_pos >= 8) {
        repeat8(parse_unicode_pre);
        self->input_pos += 8;
        continue;
        repeat8(parse_unicode_post);
    }
    while (true) {
        if (MS_UNLIKELY(self->input_pos == self->input_end)) return ms_err_truncated();
        if (MS_UNLIKELY(char_is_special(*self->input_pos))) break;
        self->input_pos++;
    }

parse_unicode_end:
    OPT_FORCE_RELOAD(*self->input_pos);

    if (MS_LIKELY(*self->input_pos == '"')) {
        self->input_pos++;
        return 0;
    }
    else if (*self->input_pos == '\\') {
        self->input_pos++;
        if (MS_UNLIKELY(self->input_pos == self->input_end)) return ms_err_truncated();

        switch (*self->input_pos) {
            case '"':
            case '\\':
            case '/':
            case 'b':
            case 'f':
            case 'n':
            case 'r':
            case 't':
                self->input_pos++;
                break;
            case 'u': {
                self->input_pos++;
                unsigned int cp;
                if (J(_read_codepoint)(self, &cp) < 0) return -1;

                if (0xDC00 <= cp && cp <= 0xDFFF) {
                    J(_err_invalid)(self, "invalid utf-16 surrogate pair");
                    return -1;
                }
                else if (0xD800 <= cp && cp <= 0xDBFF) {
                    /* utf-16 pair, parse 2nd pair */
                    unsigned int cp2;
                    if (!J(_remaining)(self, 6)) return ms_err_truncated();
                    if (self->input_pos[0] != '\\' || self->input_pos[1] != 'u') {
                        J(_err_invalid)(self, "unexpected end of hex escape");
                        return -1;
                    }
                    self->input_pos += 2;
                    if (J(_read_codepoint)(self, &cp2) < 0) return -1;
                    if (cp2 < 0xDC00 || cp2 > 0xDFFF) {
                        J(_err_invalid)(self, "invalid utf-16 surrogate pair");
                        return -1;
                    }
                    cp = 0x10000 + (((cp - 0xD800) << 10) | (cp2 - 0xDC00));
                }
                break;
            }
            default: {
                J(_err_invalid)(self, "invalid escaped character");
                return -1;
            }
        }
        goto parse_unicode;
    }
    else {
        J(_err_invalid)(self, "invalid character");
        return -1;
    }
}

#undef parse_ascii_pre
#undef parse_ascii_post
#undef parse_unicode_pre
#undef parse_unicode_post

#ifndef MSGSPEC_JSON_SHARED_BASE64_TABLE
#define MSGSPEC_JSON_SHARED_BASE64_TABLE
/* A table of the corresponding base64 value for each character, or -1 if an
 * invalid character in the base64 alphabet (note the padding char '=' is
 * handled elsewhere, so is marked as invalid here as well) */
static const uint8_t base64_decode_table[] = {
    -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1,
    -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1,
    -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,62, -1,-1,-1,63,
    52,53,54,55, 56,57,58,59, 60,61,-1,-1, -1,-1,-1,-1,
    -1, 0, 1, 2,  3, 4, 5, 6,  7, 8, 9,10, 11,12,13,14,
    15,16,17,18, 19,20,21,22, 23,24,25,-1, -1,-1,-1,-1,
    -1,26,27,28, 29,30,31,32, 33,34,35,36, 37,38,39,40,
    41,42,43,44, 45,46,47,48, 49,50,51,-1, -1,-1,-1,-1,
    -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1,
    -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1,
    -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1,
    -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1,
    -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1,
    -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1,
    -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1,
    -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1, -1,-1,-1,-1,
};
#endif

static PyObject *
J(_decode_binary)(
    const char *buffer, Py_ssize_t size, TypeNode *type, PathNode *path
) {
    PyObject *out = NULL;
    char *bin_buffer;
    Py_ssize_t bin_size, i;

    if (size % 4 != 0) goto invalid;

    int npad = 0;
    if (size > 0 && buffer[size - 1] == '=') npad++;
    if (size > 1 && buffer[size - 2] == '=') npad++;

    bin_size = (size / 4) * 3 - npad;
    if (!ms_passes_bytes_constraints(bin_size, type, path)) return NULL;

    if (type->types & MS_TYPE_BYTES) {
        out = PyBytes_FromStringAndSize(NULL, bin_size);
        if (out == NULL) return NULL;
        bin_buffer = PyBytes_AS_STRING(out);
    }
    else if (type->types & MS_TYPE_BYTEARRAY) {
        out = PyByteArray_FromStringAndSize(NULL, bin_size);
        if (out == NULL) return NULL;
        bin_buffer = PyByteArray_AS_STRING(out);
    }
    else {
        PyObject *temp = PyBytes_FromStringAndSize(NULL, bin_size);
        if (temp == NULL) return NULL;
        bin_buffer = PyBytes_AS_STRING(temp);
        out = PyMemoryView_FromObject(temp);
        Py_DECREF(temp);
        if (out == NULL) return NULL;
    }

    int quad = 0;
    uint8_t left_c = 0;
    for (i = 0; i < size - npad; i++) {
        uint8_t c = base64_decode_table[(uint8_t)(buffer[i])];
        if (c >= 64) goto invalid;

        switch (quad) {
            case 0:
                quad = 1;
                left_c = c;
                break;
            case 1:
                quad = 2;
                *bin_buffer++ = (left_c << 2) | (c >> 4);
                left_c = c & 0x0f;
                break;
            case 2:
                quad = 3;
                *bin_buffer++ = (left_c << 4) | (c >> 2);
                left_c = c & 0x03;
                break;
            case 3:
                quad = 0;
                *bin_buffer++ = (left_c << 6) | c;
                left_c = 0;
                break;
        }
    }
    return out;

invalid:
    Py_XDECREF(out);
    return ms_error_with_path("Invalid base64 encoded string%U", path);
}

static PyObject *
J(_decode_string)(JSONDecoderState *self, TypeNode *type, PathNode *path) {
    char *view = NULL;
    bool is_ascii = true;
    Py_ssize_t size = J(_decode_string_view)(self, &view, &is_ascii);
    if (size < 0) return NULL;

    if (MS_LIKELY(type->types & (MS_TYPE_STR | MS_TYPE_ANY))) {
        PyObject *out;
        if (MS_LIKELY(is_ascii)) {
            out = PyUnicode_New(size, 127);
            memcpy(ascii_get_buffer(out), view, size);
        }
        else {
            out = PyUnicode_DecodeUTF8(view, size, NULL);
        }
        return ms_check_str_constraints(out, type, path);
    }
    else if (MS_UNLIKELY(!self->strict)) {
        bool invalid = false;
        PyObject *out = ms_decode_str_lax(view, size, type, path, &invalid);
        if (!invalid) return out;
    }

    if (MS_UNLIKELY(type->types & MS_TYPE_DATETIME)) {
        return ms_decode_datetime_from_str(view, size, type, path);
    }
    else if (MS_UNLIKELY(type->types & MS_TYPE_DATE)) {
        return ms_decode_date(view, size, path);
    }
    else if (MS_UNLIKELY(type->types & MS_TYPE_TIME)) {
        return ms_decode_time(view, size, type, path);
    }
    else if (MS_UNLIKELY(type->types & MS_TYPE_TIMEDELTA)) {
        return ms_decode_timedelta(view, size, type, path);
    }
    else if (MS_UNLIKELY(type->types & MS_TYPE_UUID)) {
        return ms_decode_uuid_from_str(view, size, path);
    }
    else if (MS_UNLIKELY(type->types & MS_TYPE_DECIMAL)) {
        return ms_decode_decimal(view, size, is_ascii, path, NULL);
    }
    else if (
        MS_UNLIKELY(type->types &
            (MS_TYPE_BYTES | MS_TYPE_BYTEARRAY | MS_TYPE_MEMORYVIEW)
        )
    ) {
        return J(_decode_binary)(view, size, type, path);
    }
    else if (MS_UNLIKELY(type->types & (MS_TYPE_ENUM | MS_TYPE_STRLITERAL))) {
        return ms_decode_str_enum_or_literal(view, size, type, path);
    }
    return ms_validation_error("str", type, path);
}

static PyObject *
J(_decode_dict_key_fallback)(
    JSONDecoderState *self,
    const char *view, Py_ssize_t size, bool is_ascii, TypeNode *type, PathNode *path
) {
    if (type->types & (MS_TYPE_STR | MS_TYPE_ANY)) {
        PyObject *out;
        if (is_ascii) {
            out = PyUnicode_New(size, 127);
            if (MS_UNLIKELY(out == NULL)) return NULL;
            memcpy(ascii_get_buffer(out), view, size);
        }
        else {
            out = PyUnicode_DecodeUTF8(view, size, NULL);
        }
        if (MS_UNLIKELY(type->types & (MS_TYPE_CUSTOM | MS_TYPE_CUSTOM_GENERIC))) {
            return ms_decode_custom(out, self->dec_hook, type, path);
        }
        return ms_check_str_constraints(out, type, path);
    }
    if (type->types & (
            MS_TYPE_INT | MS_TYPE_INTENUM | MS_TYPE_INTLITERAL |
            MS_TYPE_FLOAT | MS_TYPE_DECIMAL |
            ((!self->strict) * (MS_TYPE_DATETIME | MS_TYPE_TIMEDELTA))
        )
    ) {
        PyObject *out;
        if (maybe_parse_number(view, size, type, path, self->strict, &out)) {
            return out;
        }
    }

    if (type->types & (MS_TYPE_ENUM | MS_TYPE_STRLITERAL)) {
        return ms_decode_str_enum_or_literal(view, size, type, path);
    }
    else if (type->types & MS_TYPE_UUID) {
        return ms_decode_uuid_from_str(view, size, path);
    }
    else if (type->types & MS_TYPE_DATETIME) {
        return ms_decode_datetime_from_str(view, size, type, path);
    }
    else if (type->types & MS_TYPE_DATE) {
        return ms_decode_date(view, size, path);
    }
    else if (type->types & MS_TYPE_TIME) {
        return ms_decode_time(view, size, type, path);
    }
    else if (type->types & MS_TYPE_TIMEDELTA) {
        return ms_decode_timedelta(view, size, type, path);
    }
    else if (type->types & (MS_TYPE_BYTES | MS_TYPE_MEMORYVIEW)) {
        return J(_decode_binary)(view, size, type, path);
    }
    else {
        return ms_validation_error("str", type, path);
    }
}

static PyObject *
J(_decode_dict_key)(JSONDecoderState *self, TypeNode *type, PathNode *path) {
    bool is_ascii = true;
    char *view = NULL;
    Py_ssize_t size;

    size = J(_decode_string_view)(self, &view, &is_ascii);
    if (size < 0) return NULL;
#ifndef Py_GIL_DISABLED
    bool is_str = type->types == MS_TYPE_ANY || type->types == MS_TYPE_STR;
    bool cacheable = is_str && is_ascii && size > 0 && size <= STRING_CACHE_MAX_STRING_LENGTH;
    if (MS_UNLIKELY(!cacheable)) {
        return J(_decode_dict_key_fallback)(self, view, size, is_ascii, type, path);
    }

    uint32_t hash = murmur2(view, size);
    uint32_t index = hash % STRING_CACHE_SIZE;
    PyObject *existing = string_cache[index];

    if (MS_LIKELY(existing != NULL)) {
        Py_ssize_t e_size = ((PyASCIIObject *)existing)->length;
        char *e_str = ascii_get_buffer(existing);
        if (MS_LIKELY(size == e_size && memcmp(view, e_str, size) == 0)) {
            Py_INCREF(existing);
            return existing;
        }
    }

    /* Create a new ASCII str object */
    PyObject *new = PyUnicode_New(size, 127);
    if (MS_UNLIKELY(new == NULL)) return NULL;
    memcpy(ascii_get_buffer(new), view, size);

    /* Swap out the str in the cache */
    Py_XDECREF(existing);
    Py_INCREF(new);
    string_cache[index] = new;
    return new;
#else
    return J(_decode_dict_key_fallback)(self, view, size, is_ascii, type, path);
#endif
}

static PyObject *
J(_decode_list)(JSONDecoderState *self, TypeNode *type, TypeNode *el_type, PathNode *path) {
    unsigned char c;
    bool first = true;
    PathNode el_path = {path, 0, NULL};

    self->input_pos++; /* Skip '[' */

    PyObject *out = PyList_New(0);
    if (out == NULL) return NULL;
    if (Py_EnterRecursiveCall(" while deserializing an object")) {
        Py_DECREF(out);
        return NULL; /* cpylint-ignore */
    }
    while (true) {
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        /* Parse ']' or ',', then peek the next character */
        if (c == ']') {
            self->input_pos++;
            break;
        }
        else if (c == ',' && !first) {
            self->input_pos++;
            if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        }
        else if (first) {
            /* Only the first item doesn't need a comma delimiter */
            first = false;
        }
        else {
            J(_err_invalid)(self, "expected ',' or ']'");
            goto error;
        }

        if (MS_UNLIKELY(c == ']')) {
            if (self->allow_trailing_commas) {
                self->input_pos++;
                break;
            }
            J(_err_invalid)(self, "trailing comma in array");
            goto error;
        }

        /* Parse item */
        PyObject *item = J(_decode)(self, el_type, &el_path);
        if (item == NULL) goto error;
        el_path.index++;

        /* Append item to list */
        if (MS_LIKELY((LIST_CAPACITY(out) > Py_SIZE(out)))) {
            PyList_SET_ITEM(out, Py_SIZE(out), item);
            Py_SET_SIZE(out, Py_SIZE(out) + 1);
        }
        else {
            int status = PyList_Append(out, item);
            Py_DECREF(item);
            if (MS_UNLIKELY(status < 0)) goto error;
        }
    }

    if (MS_UNLIKELY(!ms_passes_array_constraints(PyList_GET_SIZE(out), type, path))) {
        goto error;
    }

    Py_LeaveRecursiveCall();
    return out;
error:
    Py_LeaveRecursiveCall();
    Py_DECREF(out);
    return NULL;
}

static PyObject *
J(_decode_set)(
    JSONDecoderState *self, TypeNode *type, TypeNode *el_type, PathNode *path
) {
    PyObject *out, *item = NULL;
    unsigned char c;
    bool first = true;
    PathNode el_path = {path, 0, NULL};

    self->input_pos++; /* Skip '[' */

    out = (type->types & MS_TYPE_SET) ?  PySet_New(NULL) : PyFrozenSet_New(NULL);
    if (out == NULL) return NULL;

    if (Py_EnterRecursiveCall(" while deserializing an object")) {
        Py_DECREF(out);
        return NULL; /* cpylint-ignore */
    }
    while (true) {
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        /* Parse ']' or ',', then peek the next character */
        if (c == ']') {
            self->input_pos++;
            break;
        }
        else if (c == ',' && !first) {
            self->input_pos++;
            if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        }
        else if (first) {
            /* Only the first item doesn't need a comma delimiter */
            first = false;
        }
        else {
            J(_err_invalid)(self, "expected ',' or ']'");
            goto error;
        }

        if (MS_UNLIKELY(c == ']')) {
            if (self->allow_trailing_commas) {
                self->input_pos++;
                break;
            }
            J(_err_invalid)(self, "trailing comma in array");
            goto error;
        }

        /* Parse item */
        item = J(_decode)(self, el_type, &el_path);
        if (item == NULL) goto error;
        el_path.index++;

        /* Append item to set */
        if (PySet_Add(out, item) < 0) goto error;
        Py_CLEAR(item);
    }

    if (MS_UNLIKELY(!ms_passes_array_constraints(PySet_GET_SIZE(out), type, path))) {
        goto error;
    }

    Py_LeaveRecursiveCall();
    return out;
error:
    Py_LeaveRecursiveCall();
    Py_DECREF(out);
    Py_XDECREF(item);
    return NULL;
}

static PyObject *
J(_decode_vartuple)(JSONDecoderState *self, TypeNode *type, TypeNode *el_type, PathNode *path) {
    PyObject *list, *item, *out = NULL;
    Py_ssize_t size, i;

    list = J(_decode_list)(self, type, el_type, path);
    if (list == NULL) return NULL;

    size = PyList_GET_SIZE(list);
    out = PyTuple_New(size);
    if (out != NULL) {
        for (i = 0; i < size; i++) {
            item = PyList_GET_ITEM(list, i);
            PyTuple_SET_ITEM(out, i, item);
            PyList_SET_ITEM(list, i, NULL);  /* Drop reference in old list */
        }
    }
    Py_DECREF(list);
    return out;
}

static PyObject *
J(_decode_fixtuple)(JSONDecoderState *self, TypeNode *type, PathNode *path) {
    PyObject *out, *item;
    unsigned char c;
    bool first = true;
    PathNode el_path = {path, 0, NULL};
    Py_ssize_t i = 0, offset, fixtuple_size;

    TypeNode_get_fixtuple(type, &offset, &fixtuple_size);

    self->input_pos++; /* Skip '[' */

    out = PyTuple_New(fixtuple_size);
    if (out == NULL) return NULL;

    if (Py_EnterRecursiveCall(" while deserializing an object")) {
        Py_DECREF(out);
        return NULL; /* cpylint-ignore */
    }

    while (true) {
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        /* Parse ']' or ',', then peek the next character */
        if (c == ']') {
            self->input_pos++;
            if (MS_UNLIKELY(i < fixtuple_size)) goto size_error;
            break;
        }
        else if (c == ',' && !first) {
            self->input_pos++;
            if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        }
        else if (first) {
            /* Only the first item doesn't need a comma delimiter */
            first = false;
        }
        else {
            J(_err_invalid)(self, "expected ',' or ']'");
            goto error;
        }

        if (MS_UNLIKELY(c == ']')) {
            if (self->allow_trailing_commas) {
                self->input_pos++;
                break;
            }
            J(_err_invalid)(self, "trailing comma in array");
            goto error;
        }

        /* Check we don't have too many elements */
        if (MS_UNLIKELY(i >= fixtuple_size)) goto size_error;

        /* Parse item */
        item = J(_decode)(self, type->details[offset + i].pointer, &el_path);
        if (item == NULL) goto error;
        el_path.index++;

        /* Add item to tuple */
        PyTuple_SET_ITEM(out, i, item);
        i++;
    }
    Py_LeaveRecursiveCall();
    return out;

size_error:
    ms_raise_validation_error(
        path,
        "Expected `array` of length %zd%U",
        fixtuple_size
    );
error:
    Py_LeaveRecursiveCall();
    Py_DECREF(out);
    return NULL;
}

static PyObject *
J(_decode_namedtuple)(JSONDecoderState *self, TypeNode *type, PathNode *path) {
    unsigned char c;
    bool first = true;
    Py_ssize_t nfields, ndefaults, nrequired;
    NamedTupleInfo *info = TypeNode_get_namedtuple_info(type);

    nfields = Py_SIZE(info);
    ndefaults = info->defaults == NULL ? 0 : PyTuple_GET_SIZE(info->defaults);
    nrequired = nfields - ndefaults;

    self->input_pos++; /* Skip '[' */

    if (Py_EnterRecursiveCall(" while deserializing an object")) return NULL;

    PyTypeObject *nt_type = (PyTypeObject *)(info->class);
    PyObject *out = nt_type->tp_alloc(nt_type, nfields);
    if (out == NULL) goto error;
    MS_TUPLE_RESET_HASH(out);
    for (Py_ssize_t i = 0; i < nfields; i++) {
        PyTuple_SET_ITEM(out, i, NULL);
    }

    Py_ssize_t i = 0;
    while (true) {
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        /* Parse ']' or ',', then peek the next character */
        if (c == ']') {
            self->input_pos++;
            if (MS_UNLIKELY(i < nrequired)) goto size_error;
            break;
        }
        else if (c == ',' && !first) {
            self->input_pos++;
            if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        }
        else if (first) {
            /* Only the first item doesn't need a comma delimiter */
            first = false;
        }
        else {
            J(_err_invalid)(self, "expected ',' or ']'");
            goto error;
        }

        if (MS_UNLIKELY(c == ']')) {
            if (self->allow_trailing_commas) {
                self->input_pos++;
                break;
            }
            J(_err_invalid)(self, "trailing comma in array");
            goto error;
        }

        /* Check we don't have too many elements */
        if (MS_UNLIKELY(i >= nfields)) goto size_error;

        /* Parse item */
        PathNode el_path = {path, i, NULL};
        PyObject *item = J(_decode)(self, info->types[i], &el_path);
        if (item == NULL) goto error;

        /* Add item to tuple */
        PyTuple_SET_ITEM(out, i, item);
        i++;
    }
    Py_LeaveRecursiveCall();

    /* Fill in defaults */
    for (; i < nfields; i++) {
        PyObject *item = PyTuple_GET_ITEM(info->defaults, i - nrequired);
        Py_INCREF(item);
        PyTuple_SET_ITEM(out, i, item);
    }

    return out;

size_error:
    if (ndefaults == 0) {
        ms_raise_validation_error(
            path,
            "Expected `array` of length %zd%U",
            nfields
        );
    }
    else {
        ms_raise_validation_error(
            path,
            "Expected `array` of length %zd to %zd%U",
            nrequired,
            nfields
        );
    }
error:
    Py_LeaveRecursiveCall();
    Py_DECREF(out);
    return NULL;
}

static PyObject *
J(_decode_struct_array_inner)(
    JSONDecoderState *self, StructInfo *info, PathNode *path,
    Py_ssize_t starting_index
) {
    Py_ssize_t nfields, ndefaults, nrequired, npos, i = 0;
    PyObject *out, *item = NULL;
    unsigned char c;
    bool is_gc, should_untrack;
    bool first = starting_index == 0;
    StructMetaObject *st_type = info->class;
    PathNode item_path = {path, starting_index};

    out = Struct_alloc((PyTypeObject *)(st_type));
    if (out == NULL) return NULL;

    nfields = PyTuple_GET_SIZE(st_type->struct_encode_fields);
    ndefaults = PyTuple_GET_SIZE(st_type->struct_defaults);
    nrequired = nfields - st_type->n_trailing_defaults;
    npos = nfields - ndefaults;
    is_gc = MS_TYPE_IS_GC(st_type);
    should_untrack = is_gc;

    if (Py_EnterRecursiveCall(" while deserializing an object")) {
        Py_DECREF(out);
        return NULL; /* cpylint-ignore */
    }
    while (true) {
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        /* Parse ']' or ',', then peek the next character */
        if (c == ']') {
            self->input_pos++;
            break;
        }
        else if (c == ',' && !first) {
            self->input_pos++;
            if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        }
        else if (first) {
            /* Only the first item doesn't need a comma delimiter */
            first = false;
        }
        else {
            J(_err_invalid)(self, "expected ',' or ']'");
            goto error;
        }

        if (MS_UNLIKELY(c == ']')) {
            if (self->allow_trailing_commas) {
                self->input_pos++;
                break;
            }
            J(_err_invalid)(self, "trailing comma in array");
            goto error;
        }

        if (MS_LIKELY(i < nfields)) {
            /* Parse item */
            item = J(_decode)(self, info->types[i], &item_path);
            if (MS_UNLIKELY(item == NULL)) goto error;
            Struct_set_index(out, i, item);
            if (should_untrack) {
                should_untrack = !MS_MAYBE_TRACKED(item);
            }
            i++;
            item_path.index++;
        }
        else {
            if (MS_UNLIKELY(st_type->forbid_unknown_fields == OPT_TRUE)) {
                ms_raise_validation_error(
                    path,
                    "Expected `array` of at most length %zd",
                    nfields
                );
                goto error;
            }
            else {
                /* Skip trailing fields */
                if (J(_skip)(self) < 0) goto error;
            }
        }
    }

    /* Check for missing required fields */
    if (i < nrequired) {
        ms_raise_validation_error(
            path,
            "Expected `array` of at least length %zd, got %zd%U",
            nrequired + starting_index,
            i + starting_index
        );
        goto error;
    }
    /* Fill in missing fields with defaults */
    for (; i < nfields; i++) {
        item = get_default(
            PyTuple_GET_ITEM(st_type->struct_defaults, i - npos)
        );
        if (item == NULL) goto error;
        Struct_set_index(out, i, item);
        if (should_untrack) {
            should_untrack = !MS_MAYBE_TRACKED(item);
        }
    }
    if (Struct_decode_post_init(st_type, out, path) < 0) goto error;
    Py_LeaveRecursiveCall();
    if (is_gc && should_untrack && MS_IS_TRACKED(out))
        PyObject_GC_UnTrack(out);
    return out;
error:
    Py_LeaveRecursiveCall();
    Py_DECREF(out);
    return NULL;
}

/* Decode an integer. If the value fits in an int64_t, it will be stored in
 * `out`, otherwise it will be stored in `uout`. A return value of -1 indicates
 * an error. */
static int
J(_decode_cint)(JSONDecoderState *self, int64_t *out, uint64_t *uout, PathNode *path) {
    uint64_t mantissa = 0;
    bool is_negative = false;
    unsigned char c;
    unsigned char *orig_input_pos = self->input_pos;

    if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) return -1;

    /* Parse minus sign (if present) */
    if (c == '-') {
        self->input_pos++;
        c = J(_peek_or_null)(self);
        is_negative = true;
    }

    /* Parse integer */
    if (MS_UNLIKELY(c == '0')) {
        /* Ensure at most one leading zero */
        self->input_pos++;
        c = J(_peek_or_null)(self);
        if (MS_UNLIKELY(is_digit(c))) {
            J(_err_invalid)(self, "invalid number");
            return -1;
        }
    }
    else {
        /* Parse the integer part of the number.
         *
         * We can read the first 19 digits safely into a uint64 without
         * checking for overflow. Removing overflow checks from the loop gives
         * a measurable performance boost. */
        size_t remaining = self->input_end - self->input_pos;
        size_t n_safe = Py_MIN(19, remaining);
        while (n_safe) {
            c = *self->input_pos;
            if (!is_digit(c)) goto end_integer;
            self->input_pos++;
            n_safe--;
            mantissa = mantissa * 10 + (uint64_t)(c - '0');
        }
        if (MS_UNLIKELY(remaining > 19)) {
            /* Reading a 20th digit may or may not cause overflow. Any
             * additional digits definitely will. Read the 20th digit (and
             * check for a 21st), taking the slow path upon overflow. */
            c = *self->input_pos;
            if (MS_UNLIKELY(is_digit(c))) {
                self->input_pos++;
                uint64_t mantissa2 = mantissa * 10 + (uint64_t)(c - '0');
                bool overflowed = (mantissa2 < mantissa) || ((mantissa2 - (uint64_t)(c - '0')) / 10) != mantissa;
                if (MS_UNLIKELY(overflowed || is_digit(J(_peek_or_null)(self)))) {
                    goto error_not_int;
                }
                mantissa = mantissa2;
                c = J(_peek_or_null)(self);
            }
        }

end_integer:
        /* There must be at least one digit */
        if (MS_UNLIKELY(mantissa == 0)) goto error_not_int;
    }

    if (c == '.' || c == 'e' || c == 'E') goto error_not_int;

    if (is_negative) {
        if (mantissa > 1ull << 63) goto error_not_int;
        *out = -1 * (int64_t)mantissa;
    }
    else {
        if (mantissa > LLONG_MAX) {
            *uout = mantissa;
        }
        else {
            *out = mantissa;
        }
    }
    return 0;

error_not_int:
    /* Use skip to catch malformed JSON */
    self->input_pos = orig_input_pos;
    if (J(_skip)(self) < 0) return -1;

    ms_error_with_path("Expected `int`%U", path);
    return -1;
}

static Py_ssize_t
J(_decode_cstr)(JSONDecoderState *self, char **out, PathNode *path) {
    unsigned char c;
    if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) return -1;
    if (c != '"') {
        /* Use skip to catch malformed JSON */
        if (J(_skip)(self) < 0) return -1;
        /* JSON is valid but the wrong type */
        ms_error_with_path("Expected `str`%U", path);
        return -1;
    }
    bool is_ascii = true;
    return J(_decode_string_view)(self, out, &is_ascii);
}

static int
J(_ensure_array_nonempty)(
    JSONDecoderState *self, StructMetaObject *st_type, PathNode *path
) {
    unsigned char c;
    /* Check for an early end to the array */
    if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) return -1;
    if (c == ']') {
        Py_ssize_t expected_size;
        if (st_type == NULL) {
            /* If we don't know the type, the most we know is that the minimum
             * size is 1 */
            expected_size = 1;
        }
        else {
            /* n_fields - n_optional_fields + 1 tag */
            expected_size = PyTuple_GET_SIZE(st_type->struct_encode_fields)
                            - PyTuple_GET_SIZE(st_type->struct_defaults)
                            + 1;
        }
        ms_raise_validation_error(
            path,
            "Expected `array` of at least length %zd, got 0%U",
            expected_size
        );
        return -1;
    }
    return 0;
}

static int
J(_ensure_tag_matches)(
    JSONDecoderState *self, PathNode *path, PyObject *expected_tag
) {
    if (PyUnicode_CheckExact(expected_tag)) {
        char *tag = NULL;
        Py_ssize_t tag_size;
        tag_size = J(_decode_cstr)(self, &tag, path);
        if (tag_size < 0) return -1;

        /* Check that tag matches expected tag value */
        Py_ssize_t expected_size;
        const char *expected_str = unicode_str_and_size_nocheck(
            expected_tag, &expected_size
        );
        if (tag_size != expected_size || memcmp(tag, expected_str, expected_size) != 0) {
            /* Tag doesn't match the expected value, error nicely */
            ms_invalid_cstr_value(tag, tag_size, path);
            return -1;
        }
    }
    else {
        int64_t tag = 0;
        uint64_t utag = 0;
        if (J(_decode_cint)(self, &tag, &utag, path) < 0) return -1;
        int64_t expected = PyLong_AsLongLong(expected_tag);
        /* Tags must be int64s, if utag != 0 then we know the tags don't match.
         * We parse the full uint64 value only to validate the message and
         * raise a nice error */
        if (utag != 0) {
            ms_invalid_cuint_value(utag, path);
            return -1;
        }
        if (tag != expected) {
            ms_invalid_cint_value(tag, path);
            return -1;
        }
    }
    return 0;
}

static StructInfo *
J(_decode_tag_and_lookup_type)(
    JSONDecoderState *self, Lookup *lookup, PathNode *path
) {
    StructInfo *out = NULL;
    if (Lookup_IsStrLookup(lookup)) {
        Py_ssize_t tag_size;
        char *tag = NULL;
        tag_size = J(_decode_cstr)(self, &tag, path);
        if (tag_size < 0) return NULL;
        out = (StructInfo *)StrLookup_Get((StrLookup *)lookup, tag, tag_size);
        if (out == NULL) {
            ms_invalid_cstr_value(tag, tag_size, path);
        }
    }
    else {
        int64_t tag = 0;
        uint64_t utag = 0;
        if (J(_decode_cint)(self, &tag, &utag, path) < 0) return NULL;
        if (utag == 0) {
            out = (StructInfo *)IntLookup_GetInt64((IntLookup *)lookup, tag);
            if (out == NULL) {
                ms_invalid_cint_value(tag, path);
            }
        }
        else {
            /* tags can't be uint64 values, we only decode to give a nice error */
            ms_invalid_cuint_value(utag, path);
        }
    }
    return out;
}

static PyObject *
J(_decode_struct_array)(
    JSONDecoderState *self, TypeNode *type, PathNode *path
) {
    Py_ssize_t starting_index = 0;
    StructInfo *info = TypeNode_get_struct_info(type);

    self->input_pos++; /* Skip '[' */

    /* If this is a tagged struct, first read and validate the tag */
    if (info->class->struct_tag_value != NULL) {
        PathNode tag_path = {path, 0};
        if (J(_ensure_array_nonempty)(self, info->class, path) < 0) return NULL;
        if (J(_ensure_tag_matches)(self, &tag_path, info->class->struct_tag_value) < 0) return NULL;
        starting_index = 1;
    }

    /* Decode the rest of the struct */
    return J(_decode_struct_array_inner)(self, info, path, starting_index);
}

static PyObject *
J(_decode_struct_array_union)(
    JSONDecoderState *self, TypeNode *type, PathNode *path
) {
    PathNode tag_path = {path, 0};
    Lookup *lookup = TypeNode_get_struct_union(type);

    self->input_pos++; /* Skip '[' */
    /* Decode & lookup struct type from tag */
    if (J(_ensure_array_nonempty)(self, NULL, path) < 0) return NULL;
    StructInfo *info = J(_decode_tag_and_lookup_type)(self, lookup, &tag_path);
    if (info == NULL) return NULL;

    /* Finish decoding the rest of the struct */
    return J(_decode_struct_array_inner)(self, info, path, 1);
}

static PyObject *
J(_decode_array)(
    JSONDecoderState *self, TypeNode *type, PathNode *path
) {
    if (type->types & MS_TYPE_ANY) {
        TypeNode type_any = {MS_TYPE_ANY};
        return J(_decode_list)(self, type, &type_any, path);
    }
    else if (type->types & MS_TYPE_LIST) {
        return J(_decode_list)(self, type, TypeNode_get_array(type), path);
    }
    else if (type->types & (MS_TYPE_SET | MS_TYPE_FROZENSET)) {
        return J(_decode_set)(self, type, TypeNode_get_array(type), path);
    }
    else if (type->types & MS_TYPE_VARTUPLE) {
        return J(_decode_vartuple)(self, type, TypeNode_get_array(type), path);
    }
    else if (type->types & MS_TYPE_FIXTUPLE) {
        return J(_decode_fixtuple)(self, type, path);
    }
    else if (type->types & MS_TYPE_NAMEDTUPLE) {
        return J(_decode_namedtuple)(self, type, path);
    }
    else if (type->types & MS_TYPE_STRUCT_ARRAY) {
        return J(_decode_struct_array)(self, type, path);
    }
    else if (type->types & MS_TYPE_STRUCT_ARRAY_UNION) {
        return J(_decode_struct_array_union)(self, type, path);
    }
    return ms_validation_error("array", type, path);
}

static PyObject *
J(_decode_dict)(
    JSONDecoderState *self, TypeNode *type, TypeNode *key_type, TypeNode *val_type, PathNode *path
) {
    PyObject *out, *key = NULL, *val = NULL;
    unsigned char c;
    bool first = true;
    PathNode key_path = {path, PATH_KEY, NULL};
    PathNode val_path = {path, PATH_ELLIPSIS, NULL};

    self->input_pos++; /* Skip '{' */

    out = PyDict_New();
    if (out == NULL) return NULL;

    if (Py_EnterRecursiveCall(" while deserializing an object")) {
        Py_DECREF(out);
        return NULL; /* cpylint-ignore */
    }
    while (true) {
        /* Parse '}' or ',', then peek the next character */
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        if (c == '}') {
            self->input_pos++;
            break;
        }
        else if (c == ',' && !first) {
            self->input_pos++;
            if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        }
        else if (first) {
            /* Only the first item doesn't need a comma delimiter */
            first = false;
        }
        else {
            J(_err_invalid)(self, "expected ',' or '}'");
            goto error;
        }

        /* Parse a string key */
        if (c == '"') {
            key = J(_decode_dict_key)(self, key_type, &key_path);
            if (key == NULL) goto error;
        }
        else if (c == '}') {
            if (self->allow_trailing_commas) {
                self->input_pos++;
                break;
            }
            J(_err_invalid)(self, "trailing comma in object");
            goto error;
        }
        else {
            J(_err_invalid)(self, "object keys must be strings");
            goto error;
        }

        /* Parse colon */
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        if (c != ':') {
            J(_err_invalid)(self, "expected ':'");
            goto error;
        }
        self->input_pos++;

        /* Parse value */
        val = J(_decode)(self, val_type, &val_path);
        if (val == NULL) goto error;

        /* Add item to dict */
        if (MS_UNLIKELY(PyDict_SetItem(out, key, val) < 0))
            goto error;
        Py_CLEAR(key);
        Py_CLEAR(val);
    }

    if (MS_UNLIKELY(!ms_passes_map_constraints(PyDict_GET_SIZE(out), type, path))) goto error;

    Py_LeaveRecursiveCall();
    return out;

error:
    Py_LeaveRecursiveCall();
    Py_XDECREF(key);
    Py_XDECREF(val);
    Py_DECREF(out);
    return NULL;
}

#if PY315_PLUS
static PyObject *
J(_decode_frozendict)(
    JSONDecoderState *self, TypeNode *type, TypeNode *key_type, TypeNode *val_type, PathNode *path
) {
    PyObject *dict = J(_decode_dict)(self, type, key_type, val_type, path);
    return _PyFrozenDict_NewSteal(dict);
}
#endif

static PyObject *
J(_decode_typeddict)(
    JSONDecoderState *self, TypeNode *type, PathNode *path
) {
    PyObject *out;
    unsigned char c;
    char *key = NULL;
    bool first = true;
    Py_ssize_t key_size, nrequired = 0, pos = 0;
    TypedDictInfo *info = TypeNode_get_typeddict_info(type);

    self->input_pos++; /* Skip '{' */

    if (Py_EnterRecursiveCall(" while deserializing an object")) return NULL;

    out = PyDict_New();
    if (out == NULL) goto error;

    while (true) {
        /* Parse '}' or ',', then peek the next character */
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        if (c == '}') {
            self->input_pos++;
            break;
        }
        else if (c == ',' && !first) {
            self->input_pos++;
            if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        }
        else if (first) {
            /* Only the first item doesn't need a comma delimiter */
            first = false;
        }
        else {
            J(_err_invalid)(self, "expected ',' or '}'");
            goto error;
        }

        /* Parse a string key */
        if (c == '"') {
            bool is_ascii = true;
            key_size = J(_decode_string_view)(self, &key, &is_ascii);
            if (key_size < 0) goto error;
        }
        else if (c == '}') {
            if (self->allow_trailing_commas) {
                self->input_pos++;
                break;
            }
            J(_err_invalid)(self, "trailing comma in object");
            goto error;
        }
        else {
            J(_err_invalid)(self, "object keys must be strings");
            goto error;
        }

        /* Parse colon */
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        if (c != ':') {
            J(_err_invalid)(self, "expected ':'");
            goto error;
        }
        self->input_pos++;

        /* Parse value */
        TypeNode *field_type;
        PyObject *field = TypedDictInfo_lookup_key(info, key, key_size, &field_type, &pos);

        if (field != NULL) {
            PathNode field_path = {path, PATH_STR, field};
            PyObject *val = J(_decode)(self, field_type, &field_path);
            if (val == NULL) goto error;
            /* We want to keep a count of required fields we've decoded. Since
             * duplicates can occur, we stash the current dict size, then only
             * increment if the dict size has changed _and_ the field is
             * required. */
            Py_ssize_t cur_size = PyDict_GET_SIZE(out);
            int status = PyDict_SetItem(out, field, val);
            /* Always decref value, no need to decref key since it's a borrowed
             * reference. */
            Py_DECREF(val);
            if (status < 0) goto error;
            if ((PyDict_GET_SIZE(out) != cur_size) && (field_type->types & MS_EXTRA_FLAG)) {
                nrequired++;
            }
        }
        else {
            /* Skip unknown fields */
            if (J(_skip)(self) < 0) goto error;
        }
    }
    if (nrequired < info->nrequired) {
        /* A required field is missing, determine which one and raise */
        TypedDictInfo_error_missing(info, out, path);
        goto error;
    }
    Py_LeaveRecursiveCall();
    return out;
error:
    Py_LeaveRecursiveCall();
    Py_DECREF(out);
    return NULL;
}

static PyObject *
J(_decode_dataclass)(
    JSONDecoderState *self, TypeNode *type, PathNode *path
) {
    PyObject *out;
    unsigned char c;
    char *key = NULL;
    bool first = true;
    Py_ssize_t key_size, pos = 0;
    DataclassInfo *info = TypeNode_get_dataclass_info(type);

    if (Py_EnterRecursiveCall(" while deserializing an object")) return NULL;

    PyTypeObject *dataclass_type = (PyTypeObject *)(info->class);
    out = dataclass_type->tp_alloc(dataclass_type, 0);
    if (out == NULL) goto error;
    if (info->pre_init != NULL) {
        PyObject *res = PyObject_CallOneArg(info->pre_init, out);
        if (res == NULL) goto error;
        Py_DECREF(res);
    }

    self->input_pos++; /* Skip '{' */

    while (true) {
        /* Parse '}' or ',', then peek the next character */
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        if (c == '}') {
            self->input_pos++;
            break;
        }
        else if (c == ',' && !first) {
            self->input_pos++;
            if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        }
        else if (first) {
            /* Only the first item doesn't need a comma delimiter */
            first = false;
        }
        else {
            J(_err_invalid)(self, "expected ',' or '}'");
            goto error;
        }

        /* Parse a string key */
        if (c == '"') {
            bool is_ascii = true;
            key_size = J(_decode_string_view)(self, &key, &is_ascii);
            if (key_size < 0) goto error;
        }
        else if (c == '}') {
            if (self->allow_trailing_commas) {
                self->input_pos++;
                break;
            }
            J(_err_invalid)(self, "trailing comma in object");
            goto error;
        }
        else {
            J(_err_invalid)(self, "object keys must be strings");
            goto error;
        }

        /* Parse colon */
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        if (c != ':') {
            J(_err_invalid)(self, "expected ':'");
            goto error;
        }
        self->input_pos++;

        /* Parse value */
        TypeNode *field_type;
        PyObject *field = DataclassInfo_lookup_key(info, key, key_size, &field_type, &pos);

        if (field != NULL) {
            PathNode field_path = {path, PATH_STR, field};
            PyObject *val = J(_decode)(self, field_type, &field_path);
            if (val == NULL) goto error;
            int status = PyObject_GenericSetAttr(out, field, val);
            Py_DECREF(val);
            if (status < 0) goto error;
        }
        else {
            /* Skip unknown fields */
            if (J(_skip)(self) < 0) goto error;
        }
    }
    if (DataclassInfo_post_decode(info, out, path) < 0) goto error;

    Py_LeaveRecursiveCall();
    return out;
error:
    Py_LeaveRecursiveCall();
    Py_XDECREF(out);
    return NULL;
}

static PyObject *
J(_decode_struct_map_inner)(
    JSONDecoderState *self, StructInfo *info, PathNode *path,
    Py_ssize_t starting_index
) {
    PyObject *out, *val = NULL;
    Py_ssize_t key_size, field_index, pos = 0;
    unsigned char c;
    char *key = NULL;
    bool first = starting_index == 0;
    StructMetaObject *st_type = info->class;
    PathNode field_path = {path, 0, (PyObject *)st_type};

    out = Struct_alloc((PyTypeObject *)(st_type));
    if (out == NULL) return NULL;

    if (Py_EnterRecursiveCall(" while deserializing an object")) {
        Py_DECREF(out);
        return NULL; /* cpylint-ignore */
    }
    while (true) {
        /* Parse '}' or ',', then peek the next character */
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        if (c == '}') {
            self->input_pos++;
            break;
        }
        else if (c == ',' && !first) {
            self->input_pos++;
            if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        }
        else if (first) {
            /* Only the first item doesn't need a comma delimiter */
            first = false;
        }
        else {
            J(_err_invalid)(self, "expected ',' or '}'");
            goto error;
        }

        /* Parse a string key */
        if (c == '"') {
            bool is_ascii = true;
            key_size = J(_decode_string_view)(self, &key, &is_ascii);
            if (key_size < 0) goto error;
        }
        else if (c == '}') {
            if (self->allow_trailing_commas) {
                self->input_pos++;
                break;
            }
            J(_err_invalid)(self, "trailing comma in object");
            goto error;
        }
        else {
            J(_err_invalid)(self, "object keys must be strings");
            goto error;
        }

        /* Parse colon */
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) goto error;
        if (c != ':') {
            J(_err_invalid)(self, "expected ':'");
            goto error;
        }
        self->input_pos++;

        /* Parse value */
        field_index = StructMeta_get_field_index(st_type, key, key_size, &pos);
        if (MS_LIKELY(field_index >= 0)) {
            field_path.index = field_index;
            TypeNode *type = info->types[field_index];
            assert(type != NULL);
            val = J(_decode)(self, type, &field_path);
            if (val == NULL) goto error;
            Struct_set_index(out, field_index, val);
        }
        else if (MS_UNLIKELY(field_index == -2)) {
            /* Decode and check that the tag value matches the expected value */
            PathNode tag_path = {path, PATH_STR, st_type->struct_tag_field};
            if (J(_ensure_tag_matches)(self, &tag_path, st_type->struct_tag_value) < 0) {
                goto error;
            }
        }
        else {
            /* Unknown field */
            if (MS_UNLIKELY(st_type->forbid_unknown_fields == OPT_TRUE)) {
                ms_error_unknown_field(key, key_size, path);
                goto error;
            }
            else {
                if (J(_skip)(self) < 0) goto error;
            }
        }
    }
    if (Struct_fill_in_defaults(st_type, out, path) < 0) goto error;
    Py_LeaveRecursiveCall();
    return out;

error:
    Py_LeaveRecursiveCall();
    Py_DECREF(out);
    return NULL;
}

static PyObject *
J(_decode_struct_map)(
    JSONDecoderState *self, TypeNode *type, PathNode *path
) {
    StructInfo *info = TypeNode_get_struct_info(type);

    self->input_pos++; /* Skip '{' */

    return J(_decode_struct_map_inner)(self, info, path, 0);
}

static PyObject *
J(_decode_struct_union)(
    JSONDecoderState *self, TypeNode *type, PathNode *path
) {
    Lookup *lookup = TypeNode_get_struct_union(type);
    PathNode tag_path = {path, PATH_STR, Lookup_tag_field(lookup)};
    Py_ssize_t tag_field_size;
    const char *tag_field = unicode_str_and_size_nocheck(
        Lookup_tag_field(lookup), &tag_field_size
    );

    self->input_pos++; /* Skip '{' */

    /* Cache the current input position in case we need to reset it once the
     * tag is found */
    unsigned char *orig_input_pos = self->input_pos;

    for (Py_ssize_t i = 0; ; i++) {
        unsigned char c;

        /* Parse '}' or ',', then peek the next character */
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) return NULL;
        if (c == '}') {
            self->input_pos++;
            break;
        }
        else if (c == ',' && (i != 0)) {
            self->input_pos++;
            if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) return NULL;
        }
        else if (i != 0) {
            return J(_err_invalid)(self, "expected ',' or '}'");
        }

        /* Parse a string key */
        Py_ssize_t key_size;
        char *key = NULL;
        if (c == '"') {
            bool is_ascii = true;
            key_size = J(_decode_string_view)(self, &key, &is_ascii);
            if (key_size < 0) return NULL;
        }
        else if (c == '}') {
            if (self->allow_trailing_commas) {
                self->input_pos++;
                break;
            }
            return J(_err_invalid)(self, "trailing comma in object");
        }
        else {
            return J(_err_invalid)(self, "object keys must be strings");
        }

        /* Check if key matches tag_field */
        bool tag_found = false;
        if (key_size == tag_field_size && memcmp(key, tag_field, key_size) == 0) {
            tag_found = true;
        }

        /* Parse colon */
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) return NULL;
        if (c != ':') {
            return J(_err_invalid)(self, "expected ':'");
        }
        self->input_pos++;

        /* Parse value */
        if (tag_found) {
            /* Decode & lookup struct type from tag */
            StructInfo *info = J(_decode_tag_and_lookup_type)(self, lookup, &tag_path);
            if (info == NULL) return NULL;
            if (i != 0) {
                /* tag wasn't first field, reset decoder position */
                self->input_pos = orig_input_pos;
            }
            return J(_decode_struct_map_inner)(self, info, path, i == 0 ? 1 : 0);
        }
        else {
            if (J(_skip)(self) < 0) return NULL;
        }
    }

    ms_missing_required_field(Lookup_tag_field(lookup), path);
    return NULL;
}

static PyObject *
J(_decode_object)(
    JSONDecoderState *self, TypeNode *type, PathNode *path
) {
    if (type->types & MS_TYPE_ANY) {
        TypeNode type_any = {MS_TYPE_ANY};
        return J(_decode_dict)(self, type, &type_any, &type_any, path);
    }
    else if (type->types & MS_ANY_DICT) {
        TypeNode *key, *val;
        TypeNode_get_dict(type, &key, &val);
#if PY315_PLUS
        if (type->types & MS_TYPE_FROZENDICT) {
            return J(_decode_frozendict)(self, type, key, val, path);
        }
#endif
        return J(_decode_dict)(self, type, key, val, path);
    }
    else if (type->types & MS_TYPE_TYPEDDICT) {
        return J(_decode_typeddict)(self, type, path);
    }
    else if (type->types & MS_TYPE_DATACLASS) {
        return J(_decode_dataclass)(self, type, path);
    }
    else if (type->types & MS_TYPE_STRUCT) {
        return J(_decode_struct_map)(self, type, path);
    }
    else if (type->types & MS_TYPE_STRUCT_UNION) {
        return J(_decode_struct_union)(self, type, path);
    }
    return ms_validation_error("object", type, path);
}

static PyObject *
J(_maybe_decode_number)(JSONDecoderState *self, TypeNode *type, PathNode *path) {
    const char *errmsg = NULL;
    const unsigned char *pout;
    PyObject *out = parse_number_inline(
        self->input_pos, self->input_end,
        &pout, &errmsg,
        type, path, self->strict, self->float_hook, false
    );
    self->input_pos = (unsigned char *)pout;

    if (MS_UNLIKELY(out == NULL)) {
        if (errmsg != NULL) {
            J(_err_invalid)(self, errmsg);
        }
    }
    return out;
}

static MS_NOINLINE PyObject *
J(_decode_raw)(JSONDecoderState *self) {
    unsigned char c;
    if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) return NULL;
    const unsigned char *start = self->input_pos;
    if (J(_skip)(self) < 0) return NULL;
    Py_ssize_t size = self->input_pos - start;
    return Raw_FromView(self->buffer_obj, (char *)start, size);
}

static MS_INLINE PyObject *
J(_decode_nocustom)(
    JSONDecoderState *self, TypeNode *type, PathNode *path
) {
    unsigned char c;

    if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) return NULL;

    switch (c) {
        case 'n': return J(_decode_none)(self, type, path);
        case 't': return J(_decode_true)(self, type, path);
        case 'f': return J(_decode_false)(self, type, path);
        case '[': return J(_decode_array)(self, type, path);
        case '{': return J(_decode_object)(self, type, path);
        case '"': return J(_decode_string)(self, type, path);
        default: return J(_maybe_decode_number)(self, type, path);
    }
}

static PyObject *
J(_decode)(
    JSONDecoderState *self, TypeNode *type, PathNode *path
) {
    if (MS_UNLIKELY(type->types == 0)) {
        return J(_decode_raw)(self);
    }
    PyObject *obj = J(_decode_nocustom)(self, type, path);
    if (MS_UNLIKELY(type->types & (MS_TYPE_CUSTOM | MS_TYPE_CUSTOM_GENERIC))) {
        return ms_decode_custom(obj, self->dec_hook, type, path);
    }
    return obj;
}

static int
J(_skip_ident)(JSONDecoderState *self, const char *ident, size_t len) {
    self->input_pos++;  /* Already checked first char */
    if (MS_UNLIKELY(!J(_remaining)(self, len))) return ms_err_truncated();
    if (memcmp(self->input_pos, ident, len) != 0) {
        J(_err_invalid)(self, "invalid character");
        return -1;
    }
    self->input_pos += len;
    return 0;
}

static int
J(_skip_array)(JSONDecoderState *self) {
    unsigned char c;
    bool first = true;
    int out = -1;

    self->input_pos++; /* Skip '[' */

    if (Py_EnterRecursiveCall(" while deserializing an object")) return -1;
    while (true) {
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) break;
        if (c == ']') {
            self->input_pos++;
            out = 0;
            break;
        }
        else if (c == ',' && !first) {
            self->input_pos++;
            if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) break;
        }
        else if (first) {
            first = false;
        }
        else {
            J(_err_invalid)(self, "expected ',' or ']'");
            break;
        }
        if (MS_UNLIKELY(c == ']')) {
            if (self->allow_trailing_commas) {
                self->input_pos++;
                out = 0;
                break;
            }
            J(_err_invalid)(self, "trailing comma in array");
            break;
        }

        if (J(_skip)(self) < 0) break;
    }
    Py_LeaveRecursiveCall();
    return out;
}

static int
J(_skip_object)(JSONDecoderState *self) {
    unsigned char c;
    bool first = true;
    int out = -1;

    self->input_pos++; /* Skip '{' */

    if (Py_EnterRecursiveCall(" while deserializing an object")) return -1;
    while (true) {
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) break;
        if (c == '}') {
            self->input_pos++;
            out = 0;
            break;
        }
        else if (c == ',' && !first) {
            self->input_pos++;
            if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) break;
        }
        else if (first) {
            first = false;
        }
        else {
            J(_err_invalid)(self, "expected ',' or '}'");
            break;
        }

        /* Skip key */
        if (c == '"') {
            if (J(_skip_string)(self) < 0) break;
        }
        else if (c == '}') {
            if (self->allow_trailing_commas) {
                self->input_pos++;
                out = 0;
                break;
            }
            J(_err_invalid)(self, "trailing comma in object");
            break;
        }
        else {
            J(_err_invalid)(self, "expected '\"'");
            break;
        }

        /* Parse colon */
        if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) break;
        if (c != ':') {
            J(_err_invalid)(self, "expected ':'");
            break;
        }
        self->input_pos++;

        /* Skip value */
        if (J(_skip)(self) < 0) break;
    }
    Py_LeaveRecursiveCall();
    return out;
}

static int
J(_maybe_skip_number)(JSONDecoderState *self) {
    /* We know there is at least one byte available when this function is
     * called */
    char c = *self->input_pos;

    /* Parse minus sign (if present) */
    if (c == '-') {
        self->input_pos++;
        c = J(_peek_or_null)(self);
    }

    /* Parse integer */
    if (MS_UNLIKELY(c == '0')) {
        /* Ensure at most one leading zero */
        self->input_pos++;
        c = J(_peek_or_null)(self);
        if (MS_UNLIKELY(is_digit(c))) {
            J(_err_invalid)(self, "invalid number");
            return -1;
        }
    }
    else {
        /* Skip the integer part of the number. */
        unsigned char *cur_pos = self->input_pos;
        while (self->input_pos < self->input_end && is_digit(*self->input_pos)) {
            self->input_pos++;
        }
        /* There must be at least one digit */
        if (MS_UNLIKELY(cur_pos == self->input_pos)) {
            J(_err_invalid)(self, "invalid character");
            return -1;
        }
    }

    c = J(_peek_or_null)(self);
    if (c == '.') {
        self->input_pos++;
        /* Skip remaining digits until invalid/unknown character */
        unsigned char *cur_pos = self->input_pos;
        while (self->input_pos < self->input_end && is_digit(*self->input_pos)) {
            self->input_pos++;
        }
        /* Error if no digits after decimal */
        if (MS_UNLIKELY(cur_pos == self->input_pos)) {
            J(_err_invalid)(self, "invalid number");
            return -1;
        }

        c = J(_peek_or_null)(self);
    }
    if (c == 'e' || c == 'E') {
        self->input_pos++;

        /* Parse exponent sign (if any) */
        c = J(_peek_or_null)(self);
        if (c == '+' || c == '-') {
            self->input_pos++;
        }

        /* Parse exponent digits */
        unsigned char *cur_pos = self->input_pos;
        while (self->input_pos < self->input_end && is_digit(*self->input_pos)) {
            self->input_pos++;
        }
        /* Error if no digits in exponent */
        if (MS_UNLIKELY(cur_pos == self->input_pos)) {
            J(_err_invalid)(self, "invalid number");
            return -1;
        }
    }
    return 0;
}

static int
J(_skip)(JSONDecoderState *self)
{
    unsigned char c;

    if (MS_UNLIKELY(!J(_peek_skip_ws)(self, &c))) return -1;

    switch (c) {
        case 'n': return J(_skip_ident)(self, "ull", 3);
        case 't': return J(_skip_ident)(self, "rue", 3);
        case 'f': return J(_skip_ident)(self, "alse", 4);
        case '"': return J(_skip_string)(self);
        case '[': return J(_skip_array)(self);
        case '{': return J(_skip_object)(self);
        default: return J(_maybe_skip_number)(self);
    }
}

static PyObject *
J(_decode_lines_inner)(JSONDecoderState *state)
{
    PathNode path = {NULL, 0, NULL};
    PyObject *out = PyList_New(0);
    if (out == NULL) return NULL;
    while (true) {
        while (true) {
            if (state->input_pos == state->input_end) goto done;
            unsigned char c = *state->input_pos;
#if JSON_ALLOW_COMMENTS
            if (c == '/' && state->input_end - state->input_pos >= 2) {
                int status = J(_consume_comment)(state);
                if (status < 0) {
                    Py_CLEAR(out);
                    goto done;
                }
                if (status > 0) continue;
            }
#endif
            if (c != ' ' && c != '\n' && c != '\r' && c != '\t') break;
            state->input_pos++;
        }
        PyObject *item = J(_decode)(state, state->type, &path);
        path.index++;
        if (item == NULL) {
            Py_CLEAR(out);
            goto done;
        }
        int status = PyList_Append(out, item);
        Py_DECREF(item);
        if (status < 0) {
            Py_CLEAR(out);
            goto done;
        }
    }
done:
    return out;
}

#undef J
#undef JSON_CAT
#undef JSON_CAT_I
