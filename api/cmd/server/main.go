// Entry point. Wires controllers ← services ← repositories and starts gin.
package main

import (
	"log/slog"
	"os"

	"github.com/gin-gonic/gin"

	"github.com/dplata/mlbsims-api/internal/config"
	"github.com/dplata/mlbsims-api/internal/controller"
	"github.com/dplata/mlbsims-api/internal/repository"
	"github.com/dplata/mlbsims-api/internal/service"
)

func main() {
	cfg := config.MustLoad()
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	// --- Repositories (concrete implementations of service interfaces) ---
	llmRepo := repository.NewLLMRepo(cfg)
	pgxPool := repository.MustNewPgxPool(cfg)
	defer pgxPool.Close()
	pitchesRepo := repository.NewPitchesRepo(pgxPool)
	queriesRepo := repository.NewQueriesRepo(pgxPool)
	cacheRepo := repository.NewLRUCache(1000)

	// --- Service (orchestration; depends only on interfaces) ---
	askSvc := service.NewAskService(service.AskDeps{
		LLM:     llmRepo,
		Pitches: pitchesRepo,
		Queries: queriesRepo,
		Cache:   cacheRepo,
		Config:  cfg,
	})

	// --- Controllers (HTTP layer) ---
	askCtl := controller.NewAskController(askSvc, cfg)

	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(corsMiddleware())
	r.GET("/health", controller.Health)
	r.POST("/ask", askCtl.Handle)

	slog.Info("server starting", "port", cfg.Port)
	if err := r.Run(":" + cfg.Port); err != nil {
		slog.Error("server crashed", "err", err)
		os.Exit(1)
	}
}

// corsMiddleware allows browsers on mlbsims.com (and localhost during dev) to
// hit the API. The frontend page lives on the static site at mlbsims.com/ask
// and POSTs here — without these headers the browser blocks the response.
func corsMiddleware() gin.HandlerFunc {
	allowed := map[string]bool{
		"https://mlbsims.com":     true,
		"https://www.mlbsims.com": true,
		"http://localhost:8000":   true,
		"http://localhost:5173":   true,
	}
	return func(c *gin.Context) {
		origin := c.GetHeader("Origin")
		if allowed[origin] {
			c.Header("Access-Control-Allow-Origin", origin)
			c.Header("Vary", "Origin")
			c.Header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
			c.Header("Access-Control-Allow-Headers", "Content-Type")
			c.Header("Access-Control-Max-Age", "3600")
		}
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	}
}
