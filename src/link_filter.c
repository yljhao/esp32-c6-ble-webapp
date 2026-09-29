/* SPDX-License-Identifier: Apache-2.0 */

#include "link_filter.h"

#include <stdbool.h>
#include <string.h>

struct word {
	const uint8_t *start;
	size_t len;
};

static bool word_is(const struct word *w, const char *text)
{
	return strlen(text) == w->len && memcmp(text, w->start, w->len) == 0;
}

/* What the shell would read as syntax inside a word: quoting, escapes and wildcards. */
static bool has_shell_syntax(const struct word *w)
{
	for (size_t i = 0; i < w->len; i++) {
		switch (w->start[i]) {
		case '"':
		case '\'':
		case '\\':
		case '*':
		case '?':
			return true;
		default:
			break;
		}
	}
	return false;
}

static bool allowed(const struct word *words, size_t count)
{
	if (word_is(&words[0], "led")) {
		return count >= 2 && (word_is(&words[1], "set") || word_is(&words[1], "get"));
	}
	return false;
}

enum link_filter_verdict link_filter_line(const uint8_t *line, size_t len, char *out,
					  size_t out_size, size_t *out_len)
{
	struct word words[LINK_FILTER_MAX_WORDS];
	size_t count = 0;
	size_t end;
	size_t pos = 0;

	/* only a whole line is judged; a line without its end is not run */
	if (len == 0 || line[len - 1] != '\n' || out_size < len + 1) {
		return LINK_FILTER_REFUSE;
	}
	end = len - 1;
	if (end > 0 && line[end - 1] == '\r') {
		end--;
	}

	/* printable ASCII and spaces only: no "\r" (Enter to the shell), tab (completion),
	 * escape sequences, backspace or bytes the shell might treat as input control
	 */
	for (size_t i = 0; i < end; i++) {
		if (line[i] < 0x20 || line[i] > 0x7e) {
			return LINK_FILTER_REFUSE;
		}
	}

	for (size_t i = 0; i < end;) {
		if (line[i] == ' ') {
			i++;
			continue;
		}
		if (count == LINK_FILTER_MAX_WORDS) {
			return LINK_FILTER_REFUSE;
		}
		words[count].start = &line[i];
		while (i < end && line[i] != ' ') {
			i++;
		}
		words[count].len = (size_t)(&line[i] - words[count].start);
		count++;
	}

	if (count == 0) {
		return LINK_FILTER_IGNORE;
	}

	for (size_t i = 0; i < count; i++) {
		if (has_shell_syntax(&words[i]) || word_is(&words[i], "-h") ||
		    word_is(&words[i], "--help")) {
			return LINK_FILTER_REFUSE;
		}
	}

	if (!allowed(words, count)) {
		return LINK_FILTER_REFUSE;
	}

	/* rebuilt from the words: the Central's own bytes never reach the shell */
	for (size_t i = 0; i < count; i++) {
		if (i > 0) {
			out[pos++] = ' ';
		}
		memcpy(&out[pos], words[i].start, words[i].len);
		pos += words[i].len;
	}
	out[pos++] = '\n';
	*out_len = pos;
	return LINK_FILTER_PASS;
}
