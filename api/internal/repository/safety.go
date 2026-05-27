// SQL safety layer — pure function, no I/O. Validates an LLM-generated SQL
// string and prepares it for execution.
//
// Defense in depth (combined with the DB role being read-only):
//   1. Single statement only — no ";" smuggling.
//   2. Must start with SELECT or WITH (no INSERT/UPDATE/DELETE/DROP/etc.)
//   3. Reject queries containing dangerous keywords (DROP, TRUNCATE, GRANT, etc.)
//   4. Append LIMIT N if not present, to cap result size.
package repository

import (
	"fmt"
	"regexp"
	"strings"
)

var (
	// Statements we allow.
	leadingSelectOrWith = regexp.MustCompile(`(?i)^\s*(SELECT|WITH)\b`)

	// Keywords that should never appear (even in CTEs / subqueries).
	dangerousKeyword = regexp.MustCompile(
		`(?i)\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|GRANT|REVOKE|ALTER|CREATE|COPY|VACUUM|ANALYZE|REINDEX|REFRESH|CALL|DO|EXECUTE|LISTEN|NOTIFY|LOCK|SET\s+ROLE|RESET\s+ROLE)\b`,
	)

	// Detects a LIMIT clause anywhere in the query (rough; good enough for v1).
	hasLimit = regexp.MustCompile(`(?i)\bLIMIT\s+\d+`)
)

// PrepareSafeSQL inspects llmSQL, rejects it if unsafe, and appends a LIMIT
// clause if none is present. Returns the SQL ready for execution.
func PrepareSafeSQL(llmSQL string, rowLimit int) (string, error) {
	q := strings.TrimSpace(llmSQL)
	q = stripTrailingSemicolons(q)

	// Reject if not a SELECT/WITH
	if !leadingSelectOrWith.MatchString(q) {
		return "", fmt.Errorf("only SELECT/WITH queries are allowed")
	}

	// Reject multi-statement (any embedded ;)
	if strings.Contains(q, ";") {
		return "", fmt.Errorf("multiple statements not allowed")
	}

	// Reject dangerous keywords
	if dangerousKeyword.MatchString(q) {
		return "", fmt.Errorf("query contains a disallowed keyword")
	}

	// Append LIMIT if missing
	if !hasLimit.MatchString(q) {
		q = fmt.Sprintf("%s LIMIT %d", q, rowLimit)
	}

	return q, nil
}

func stripTrailingSemicolons(s string) string {
	for strings.HasSuffix(s, ";") {
		s = strings.TrimSuffix(s, ";")
		s = strings.TrimRight(s, " \t\n")
	}
	return s
}
