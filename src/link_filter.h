/* SPDX-License-Identifier: Apache-2.0 */
#ifndef LINK_FILTER_H
#define LINK_FILTER_H

#include <stddef.h>
#include <stdint.h>

/*
 * The command restriction of the Shell link (spec: Shell link command restriction, ticket 08) as
 * a decision (pure C, no Zephyr: it runs in the host suite tests/link_filter).
 *
 * Every line a Central writes is judged here before any byte of it reaches the shell. Only the
 * allow-list below gets through, and what gets through is rebuilt from the words (single spaces,
 * one "\n"), never the Central's own bytes, so a control character, a second line smuggled with
 * a "\r", an escape sequence or a quoting trick cannot reach the shell. Allowed:
 *
 *   led set <args...>     the led group (led_command.c answers with "LED <n>" or "ERR ...")
 *   led get <args...>     the read-only status: the Brightness
 *
 * ADR-0001: never kernel or device commands, so no shell built-in is on the list; a later
 * read-only status command of the application's own goes into allowed() in link_filter.c.
 * Everything else, including a bare `led`, `led <other>`, a help request (-h, --help), quoting,
 * wildcards, control or non-ASCII bytes, and more than LINK_FILTER_MAX_WORDS words, is refused
 * with LINK_FILTER_REFUSAL. The serial shell does not use this filter and keeps every command.
 */

/* The line the Central reads for a refused command (wire contract: a line starting "ERR "). */
#define LINK_FILTER_REFUSAL "ERR command not allowed"

/* Longest command accepted, in words: `led set <n>` is 3, so this leaves room for stray extra
 * words that led_command.c answers with "ERR too many arguments" (the ordinary mistake), and
 * stays far below the shell's own limit CONFIG_SHELL_ARGC_MAX (20), where it would print text.
 */
#define LINK_FILTER_MAX_WORDS 8

enum link_filter_verdict {
	LINK_FILTER_IGNORE, /* nothing to run (an empty line): print nothing */
	LINK_FILTER_PASS,   /* run `out` (rebuilt, ends with "\n") */
	LINK_FILTER_REFUSE, /* print LINK_FILTER_REFUSAL, run nothing */
};

/*
 * Judge one line: `line` holds `len` bytes up to and including the final "\n" (a "\r" right
 * before that "\n" is tolerated). `out` needs at least `len + 1` bytes; on PASS it receives the
 * rebuilt line and `*out_len` its length. On other verdicts `out` and `*out_len` are unspecified,
 * so a caller must not use them.
 */
enum link_filter_verdict link_filter_line(const uint8_t *line, size_t len, char *out,
					  size_t out_size, size_t *out_len);

#endif /* LINK_FILTER_H */
