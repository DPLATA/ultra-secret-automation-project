// GET /health — Cloud Run health probe. Returns 200 if the process is up.
// Does NOT check DB / Anthropic connectivity (those are slow + we want the
// instance to stay "healthy" during transient upstream blips so Cloud Run
// doesn't restart us mid-request).
package controller

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

func Health(g *gin.Context) {
	g.JSON(http.StatusOK, gin.H{"status": "ok"})
}
