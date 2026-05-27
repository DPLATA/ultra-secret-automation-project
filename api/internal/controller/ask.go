// POST /ask handler. Thin: parse + validate + delegate + format response.
package controller

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"

	"github.com/gin-gonic/gin"

	"github.com/dplata/mlbsims-api/internal/config"
	"github.com/dplata/mlbsims-api/internal/domain"
	"github.com/dplata/mlbsims-api/internal/service"
)

type AskController struct {
	svc *service.AskService
	cfg *config.Config
}

func NewAskController(svc *service.AskService, cfg *config.Config) *AskController {
	return &AskController{svc: svc, cfg: cfg}
}

type askRequest struct {
	Question string `json:"q" binding:"required,min=3,max=500"`
}

// Handle reads the question, calls the service, and either responds with
// JSON (error / cached) or streams Server-Sent Events (live answer).
func (c *AskController) Handle(g *gin.Context) {
	var req askRequest
	if err := g.ShouldBindJSON(&req); err != nil {
		g.JSON(http.StatusBadRequest, gin.H{"error": "invalid input"})
		return
	}

	ipHash := hashIP(g.ClientIP(), c.cfg.IPHashSecret)
	ctx := g.Request.Context()

	answer, err := c.svc.Ask(ctx, ipHash, req.Question)
	if err != nil {
		c.respondError(g, err)
		return
	}

	// Stream the summary via SSE. Data + SQL are flushed first as a single
	// event; subsequent events stream the natural-language summary chunks.
	c.streamAnswer(g, answer)
}

func (c *AskController) respondError(g *gin.Context, err error) {
	switch {
	case errors.Is(err, domain.ErrRateLimitExceeded):
		g.JSON(http.StatusTooManyRequests, gin.H{"error": "daily limit reached, try tomorrow"})
	case errors.Is(err, domain.ErrUnsafeSQL):
		g.JSON(http.StatusUnprocessableEntity, gin.H{"error": "couldn't answer that — try rephrasing"})
	case errors.Is(err, domain.ErrSQLExecution):
		g.JSON(http.StatusUnprocessableEntity, gin.H{"error": "query failed or timed out — try narrowing the question"})
	case errors.Is(err, domain.ErrLLMUnavailable):
		g.JSON(http.StatusServiceUnavailable, gin.H{"error": "temporarily unavailable, try again in a moment"})
	case errors.Is(err, domain.ErrFeatureDisabled):
		g.JSON(http.StatusServiceUnavailable, gin.H{"error": "feature is temporarily disabled"})
	default:
		g.JSON(http.StatusInternalServerError, gin.H{"error": "internal error"})
	}
}

// streamAnswer writes the data payload as the first SSE event, then streams
// the LLM-generated summary as subsequent events. The client uses EventSource
// or fetch+ReadableStream to consume.
func (c *AskController) streamAnswer(g *gin.Context, answer *domain.Answer) {
	g.Writer.Header().Set("Content-Type", "text/event-stream")
	g.Writer.Header().Set("Cache-Control", "no-cache")
	g.Writer.Header().Set("Connection", "keep-alive")

	// First event: SQL + rows as JSON
	g.SSEvent("data", answer)
	g.Writer.Flush()

	// Subsequent events: summary chunks streamed from LLM
	summaryCh, err := c.svc.StreamSummary(g.Request.Context(), answer)
	if err != nil {
		g.SSEvent("error", gin.H{"error": "summary stream failed"})
		return
	}

	g.Stream(func(w io.Writer) bool {
		chunk, ok := <-summaryCh
		if !ok {
			g.SSEvent("done", gin.H{})
			return false
		}
		g.SSEvent("summary", chunk)
		return true
	})
}

// hashIP keeps raw IPs out of the queries log. Same IP + same secret → same hash.
func hashIP(ip, secret string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(ip))
	return hex.EncodeToString(mac.Sum(nil))
}

// (unused) silences linter for the io import until streamAnswer is implemented.
var _ = fmt.Sprintf
