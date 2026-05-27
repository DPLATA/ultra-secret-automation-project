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
	r.GET("/health", controller.Health)
	r.POST("/ask", askCtl.Handle)

	slog.Info("server starting", "port", cfg.Port)
	if err := r.Run(":" + cfg.Port); err != nil {
		slog.Error("server crashed", "err", err)
		os.Exit(1)
	}
}
