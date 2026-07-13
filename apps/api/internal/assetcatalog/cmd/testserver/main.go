package main

import (
	"database/sql"
	"log"
	"net/http"
	"os"
	"strings"

	_ "github.com/jackc/pgx/v5/stdlib"
	"mirofish-novel/apps/api/internal/assetcatalog"
)

func main() {
	databaseURL := strings.TrimSpace(os.Getenv("DATABASE_URL"))
	if databaseURL == "" {
		log.Fatal("DATABASE_URL is required")
	}
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		log.Fatal(err)
	}
	defer db.Close()
	ownerID := strings.TrimSpace(os.Getenv("ASSET_CATALOG_TEST_OWNER_ID"))
	handler := assetcatalog.NewHandler(assetcatalog.NewSQLStore(db))
	wrapped := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/auth/csrf-token" {
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"csrf_token":"asset-catalog-live-csrf"}`))
			return
		}
		parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
		projectID := ""
		if len(parts) >= 3 && parts[0] == "v1" && parts[1] == "projects" {
			projectID = parts[2]
		}
		actorID := strings.TrimSpace(r.Header.Get("X-User-Id"))
		if cookie, err := r.Cookie("mirofish_session"); err == nil {
			if cookie.Value == "owner" {
				actorID = ownerID
			} else {
				actorID = "a3000000-0000-4000-8000-000000000002"
			}
		}
		permissions := map[assetcatalog.Permission]bool{}
		if actorID != "" && actorID == ownerID {
			permissions[assetcatalog.PermissionReadPrivate] = true
			permissions[assetcatalog.PermissionMutate] = true
			permissions[assetcatalog.PermissionCollections] = true
		}
		scope := assetcatalog.RequestScope{ActorID: actorID, TenantID: strings.TrimSpace(r.Header.Get("X-Tenant-Id")), ProjectID: projectID, Permissions: permissions}
		handler.ServeHTTP(w, r.WithContext(assetcatalog.WithRequestScope(r.Context(), scope)))
	})
	address := strings.TrimSpace(os.Getenv("ASSET_CATALOG_TEST_ADDRESS"))
	if address == "" {
		address = "127.0.0.1:4188"
	}
	log.Printf("asset catalog test server listening on %s", address)
	log.Fatal(http.ListenAndServe(address, wrapped))
}
