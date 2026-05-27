// Sentinel errors. Layers above repository use errors.Is to check these
// instead of pattern-matching error strings.
package domain

import "errors"

var (
	ErrRateLimitExceeded = errors.New("rate limit exceeded")
	ErrUnsafeSQL         = errors.New("generated SQL was rejected by safety layer")
	ErrSQLExecution      = errors.New("database query failed or timed out")
	ErrLLMUnavailable    = errors.New("LLM upstream call failed")
	ErrFeatureDisabled   = errors.New("feature is currently disabled via kill switch")
)
