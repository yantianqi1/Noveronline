package auth

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"testing"
)

func TestSQLReaderReturnsPublicCurrentUserWithActiveTenantsAndProjects(t *testing.T) {
	queryer := &fakeAuthQueryer{
		rows: []SQLRows{
			&fakeAuthRows{rows: [][]any{{
				"user-123",
				"author@example.test",
				"Author",
				"https://cdn.example.test/avatar.png",
			}}},
			&fakeAuthRows{rows: [][]any{
				{"tenant-123", "Studio", "owner", "active"},
				{"tenant-456", "Side Studio", "writer", "active"},
			}},
			&fakeAuthRows{rows: [][]any{
				{"tenant-123", "project-123", "Long Novel", "editor", "owner", "active"},
				{"tenant-456", "project-456", "Side Story", nil, "writer", "active"},
			}},
		},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	currentUser, err := reader.GetCurrentUser(context.Background(), GetCurrentUserInput{UserID: " user-123 "})

	if err != nil {
		t.Fatalf("GetCurrentUser returned error: %v", err)
	}
	if currentUser.User != (UserSummary{
		UserID:      "user-123",
		Email:       "author@example.test",
		DisplayName: "Author",
		AvatarURL:   "https://cdn.example.test/avatar.png",
	}) {
		t.Fatalf("unexpected user summary: %#v", currentUser.User)
	}
	if len(currentUser.ActiveTenants) != 2 {
		t.Fatalf("expected two active tenants, got %#v", currentUser.ActiveTenants)
	}
	if currentUser.ActiveTenants[0] != (TenantMembershipSummary{TenantID: "tenant-123", Name: "Studio", Role: "owner", Status: "active"}) {
		t.Fatalf("unexpected first tenant: %#v", currentUser.ActiveTenants[0])
	}
	if len(currentUser.ActiveProjects) != 2 {
		t.Fatalf("expected two active projects, got %#v", currentUser.ActiveProjects)
	}
	if currentUser.ActiveProjects[0] != (ProjectMembershipSummary{TenantID: "tenant-123", ProjectID: "project-123", Name: "Long Novel", Role: "editor", Status: "active"}) {
		t.Fatalf("unexpected explicit project role: %#v", currentUser.ActiveProjects[0])
	}
	if currentUser.ActiveProjects[1] != (ProjectMembershipSummary{TenantID: "tenant-456", ProjectID: "project-456", Name: "Side Story", Role: "writer", Status: "active"}) {
		t.Fatalf("unexpected inherited tenant role: %#v", currentUser.ActiveProjects[1])
	}
	for _, query := range queryer.queries {
		for _, forbidden := range []string{
			"api_key",
			"encrypted",
			"credential_ref",
			"object_key",
			"content_text",
			"body",
			"draft",
			"manuscript",
			"prompt",
			"response",
		} {
			if strings.Contains(strings.ToLower(query), forbidden) {
				t.Fatalf("auth lookup query selected forbidden field name %q: %s", forbidden, query)
			}
		}
	}
}

func TestSQLReaderActiveProjectsQueryFiltersInactiveProjectMemberOverrides(t *testing.T) {
	queryer := &fakeAuthQueryer{
		rows: []SQLRows{
			&fakeAuthRows{rows: [][]any{{
				"user-123",
				"author@example.test",
				"Author",
				"",
			}}},
			&fakeAuthRows{rows: [][]any{{"tenant-123", "Studio", "writer", "active"}}},
			&fakeAuthRows{rows: [][]any{{"tenant-123", "project-123", "Long Novel", nil, "writer", "active"}}},
		},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	_, err := reader.GetCurrentUser(context.Background(), GetCurrentUserInput{UserID: "user-123"})

	if err != nil {
		t.Fatalf("GetCurrentUser returned error: %v", err)
	}
	if len(queryer.queries) != 3 {
		t.Fatalf("expected user, tenant, and project queries, got %d", len(queryer.queries))
	}
	projectQuery := strings.ToLower(queryer.queries[2])
	if !strings.Contains(projectQuery, "left join project_members pm") {
		t.Fatalf("expected project query to left join project_members: %s", queryer.queries[2])
	}
	if !strings.Contains(projectQuery, "pm.status = 'active'") {
		t.Fatalf("project member override join must filter active rows: %s", queryer.queries[2])
	}
}

func TestSQLReaderMapsInactiveOrMissingUserToUserNotFound(t *testing.T) {
	queryer := &fakeAuthQueryer{
		rows: []SQLRows{&fakeAuthRows{}},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	_, err := reader.GetCurrentUser(context.Background(), GetCurrentUserInput{UserID: "user-missing"})

	assertAuthError(t, err, CodeUserNotFound, "current user was not found")
}

func TestSQLReaderSanitizesQueryScanRowsAndCloseFailures(t *testing.T) {
	maliciousErr := errors.New("driver leaked prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=projects/private content_text=secret body=secret draft=private manuscript=private response=raw")
	tests := []struct {
		name    string
		queryer *fakeAuthQueryer
	}{
		{
			name: "query",
			queryer: &fakeAuthQueryer{
				errs: []error{maliciousErr},
			},
		},
		{
			name: "scan",
			queryer: &fakeAuthQueryer{
				rows: []SQLRows{&fakeAuthRows{rows: [][]any{{"user-123"}}, scanErr: maliciousErr}},
			},
		},
		{
			name: "rows",
			queryer: &fakeAuthQueryer{
				rows: []SQLRows{&fakeAuthRows{err: maliciousErr}},
			},
		},
		{
			name: "close",
			queryer: &fakeAuthQueryer{
				rows: []SQLRows{&fakeAuthRows{closeErr: maliciousErr}},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			reader := NewSQLReader(SQLReaderConfig{Queryer: tt.queryer})

			_, err := reader.GetCurrentUser(context.Background(), GetCurrentUserInput{UserID: "user-123"})

			assertAuthError(t, err, CodeLookupFailed, "auth lookup failed")
			for _, forbidden := range []string{
				"prompt",
				"api_key",
				"sk-hidden",
				"credential_ref",
				"object_key",
				"content_text",
				"body",
				"draft",
				"manuscript",
				"response",
			} {
				if strings.Contains(err.Error(), forbidden) {
					t.Fatalf("sanitized auth error leaked %q: %v", forbidden, err)
				}
			}
		})
	}
}

func TestReaderBackedAuthorizerProjectReadRoleMatrix(t *testing.T) {
	allowedProjectRoles := []string{"project_owner", "editor", "writer", "analyst", "viewer"}
	for _, role := range allowedProjectRoles {
		t.Run("project_"+role, func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithProjectRole(role)))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionProjectRead,
			})

			if err != nil {
				t.Fatalf("expected role %q to read project: %v", role, err)
			}
		})
	}

	resolvedTenantRoles := []string{"owner", "admin", "editor", "writer", "viewer"}
	for _, role := range resolvedTenantRoles {
		t.Run("resolved_tenant_"+role, func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithProjectRole(role)))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionProjectRead,
			})

			if err != nil {
				t.Fatalf("expected resolved role %q to read project: %v", role, err)
			}
		})
	}

	authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithProjectRole("billing")))

	err := authorizer.Authorize(context.Background(), AuthorizeInput{
		UserID:     "user-123",
		TenantID:   "tenant-123",
		ProjectID:  "project-123",
		Permission: PermissionProjectRead,
	})

	assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
}

func TestReaderBackedAuthorizerTraceFullAccessRoleMatrix(t *testing.T) {
	for _, role := range []string{"project_owner", "editor"} {
		t.Run("project_"+role, func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithProjectRole(role)))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionTraceFullAccess,
			})

			if err != nil {
				t.Fatalf("expected project role %q to view full trace: %v", role, err)
			}
		})
	}

	for _, role := range []string{"owner", "admin", "editor"} {
		t.Run("tenant_"+role+"_with_matching_resolved_project", func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(CurrentUser{
				User:          UserSummary{UserID: "user-123"},
				ActiveTenants: []TenantMembershipSummary{{TenantID: "tenant-123", Role: role, Status: "active"}},
				ActiveProjects: []ProjectMembershipSummary{{
					TenantID:  "tenant-123",
					ProjectID: "project-123",
					Role:      role,
					Status:    "active",
				}},
			}))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionTraceFullAccess,
			})

			if err != nil {
				t.Fatalf("expected tenant role %q to view full trace: %v", role, err)
			}
		})
	}

	for _, role := range []string{"owner", "admin", "editor"} {
		t.Run("tenant_"+role+"_without_matching_project_denies", func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithTenantRole(role)))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionTraceFullAccess,
			})

			assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
		})
	}

	for _, role := range []string{"writer", "analyst", "viewer", "billing"} {
		t.Run("project_"+role, func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithProjectRole(role)))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionTraceFullAccess,
			})

			assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
		})
	}

	for _, role := range []string{"writer", "analyst", "viewer", "billing"} {
		t.Run("tenant_"+role, func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithTenantRole(role)))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionTraceFullAccess,
			})

			assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
		})
	}

	for _, tenantRole := range []string{"owner", "admin", "editor"} {
		for _, projectRole := range []string{"writer", "analyst", "viewer"} {
			t.Run("tenant_"+tenantRole+"_project_override_"+projectRole+"_denies", func(t *testing.T) {
				authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(CurrentUser{
					User:          UserSummary{UserID: "user-123"},
					ActiveTenants: []TenantMembershipSummary{{TenantID: "tenant-123", Role: tenantRole, Status: "active"}},
					ActiveProjects: []ProjectMembershipSummary{{
						TenantID:  "tenant-123",
						ProjectID: "project-123",
						Role:      projectRole,
						Status:    "active",
					}},
				}))

				err := authorizer.Authorize(context.Background(), AuthorizeInput{
					UserID:     "user-123",
					TenantID:   "tenant-123",
					ProjectID:  "project-123",
					Permission: PermissionTraceFullAccess,
				})

				assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
			})
		}
	}

	tests := []struct {
		name string
		user CurrentUser
	}{
		{
			name: "blank_project_status_denies",
			user: authCurrentUserWithProjectRoleAndStatus("project_owner", ""),
		},
		{
			name: "inactive_project_status_denies",
			user: authCurrentUserWithProjectRoleAndStatus("editor", "inactive"),
		},
		{
			name: "blank_tenant_status_denies",
			user: CurrentUser{
				User:          UserSummary{UserID: "user-123"},
				ActiveTenants: []TenantMembershipSummary{{TenantID: "tenant-123", Role: "owner", Status: ""}},
			},
		},
		{
			name: "inactive_tenant_status_denies",
			user: CurrentUser{
				User:          UserSummary{UserID: "user-123"},
				ActiveTenants: []TenantMembershipSummary{{TenantID: "tenant-123", Role: "admin", Status: "inactive"}},
			},
		},
		{
			name: "project_role_requires_matching_project",
			user: CurrentUser{
				User: UserSummary{UserID: "user-123"},
				ActiveProjects: []ProjectMembershipSummary{{
					TenantID:  "tenant-123",
					ProjectID: "other-project",
					Role:      "project_owner",
					Status:    "active",
				}},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(tt.user))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionTraceFullAccess,
			})

			assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
		})
	}
}

func TestReaderBackedAuthorizerWriterRunRoleMatrix(t *testing.T) {
	allowedProjectRoles := []string{"project_owner", "editor", "writer"}
	for _, role := range allowedProjectRoles {
		t.Run("project_"+role, func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithProjectRole(role)))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionWriterRun,
			})

			if err != nil {
				t.Fatalf("expected role %q to run writer: %v", role, err)
			}
		})
	}

	deniedProjectRoles := []string{"analyst", "viewer", "billing"}
	for _, role := range deniedProjectRoles {
		t.Run("project_"+role, func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithProjectRole(role)))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionWriterRun,
			})

			assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
		})
	}
}

func TestReaderBackedAuthorizerCreativeWriteRoleMatrix(t *testing.T) {
	for _, role := range []string{"project_owner", "owner", "admin", "editor", "writer"} {
		t.Run("project_"+role, func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithProjectRole(role)))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionCreativeWrite,
			})

			if err != nil {
				t.Fatalf("expected resolved project role %q to write creative state: %v", role, err)
			}
		})
	}

	for _, role := range []string{"analyst", "viewer", "billing", ""} {
		t.Run("project_"+role+"_denied", func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithProjectRole(role)))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionCreativeWrite,
			})

			assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
		})
	}

	tests := []struct {
		name string
		user CurrentUser
	}{
		{
			name: "inactive_project_status_denies",
			user: authCurrentUserWithProjectRoleAndStatus("writer", "inactive"),
		},
		{
			name: "blank_project_status_denies",
			user: authCurrentUserWithProjectRoleAndStatus("editor", ""),
		},
		{
			name: "raw_tenant_role_without_matching_project_denies",
			user: authCurrentUserWithTenantRole("owner"),
		},
		{
			name: "different_project_denies",
			user: CurrentUser{
				User: UserSummary{UserID: "user-123"},
				ActiveProjects: []ProjectMembershipSummary{{
					TenantID:  "tenant-123",
					ProjectID: "other-project",
					Role:      "project_owner",
					Status:    "active",
				}},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(tt.user))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionCreativeWrite,
			})

			assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
		})
	}
}

func TestReaderBackedAuthorizerAssetManageRoleMatrix(t *testing.T) {
	for _, role := range []string{"project_owner", "owner", "admin", "editor"} {
		t.Run("project_"+role, func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithProjectRole(role)))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionAssetManage,
			})

			if err != nil {
				t.Fatalf("expected resolved project role %q to manage assets: %v", role, err)
			}
		})
	}

	for _, role := range []string{"writer", "analyst", "viewer", "billing", ""} {
		t.Run("project_"+role+"_denied", func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithProjectRole(role)))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionAssetManage,
			})

			assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
		})
	}

	t.Run("inactive_project_status_denies", func(t *testing.T) {
		authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithProjectRoleAndStatus("editor", "inactive")))

		err := authorizer.Authorize(context.Background(), AuthorizeInput{
			UserID:     "user-123",
			TenantID:   "tenant-123",
			ProjectID:  "project-123",
			Permission: PermissionAssetManage,
		})

		assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
	})

	t.Run("blank_project_status_denies", func(t *testing.T) {
		authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithProjectRoleAndStatus("project_owner", "")))

		err := authorizer.Authorize(context.Background(), AuthorizeInput{
			UserID:     "user-123",
			TenantID:   "tenant-123",
			ProjectID:  "project-123",
			Permission: PermissionAssetManage,
		})

		assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
	})

	t.Run("matching_tenant_role_without_matching_project_denies", func(t *testing.T) {
		authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithTenantRole("owner")))

		err := authorizer.Authorize(context.Background(), AuthorizeInput{
			UserID:     "user-123",
			TenantID:   "tenant-123",
			ProjectID:  "project-123",
			Permission: PermissionAssetManage,
		})

		assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
	})

	t.Run("different_project_denies", func(t *testing.T) {
		authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(CurrentUser{
			User: UserSummary{UserID: "user-123"},
			ActiveProjects: []ProjectMembershipSummary{{
				TenantID:  "tenant-123",
				ProjectID: "other-project",
				Role:      "project_owner",
				Status:    "active",
			}},
		}))

		err := authorizer.Authorize(context.Background(), AuthorizeInput{
			UserID:     "user-123",
			TenantID:   "tenant-123",
			ProjectID:  "project-123",
			Permission: PermissionAssetManage,
		})

		assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
	})
}

func TestReaderBackedAuthorizerProjectScopedPermissionsUseResolvedProjectRole(t *testing.T) {
	tests := []struct {
		name       string
		user       CurrentUser
		permission Permission
	}{
		{
			name: "tenant_editor_project_override_viewer_denied_writer_run",
			user: CurrentUser{
				User:          UserSummary{UserID: "user-123"},
				ActiveTenants: []TenantMembershipSummary{{TenantID: "tenant-123", Role: "editor", Status: "active"}},
				ActiveProjects: []ProjectMembershipSummary{{
					TenantID:  "tenant-123",
					ProjectID: "project-123",
					Role:      "viewer",
					Status:    "active",
				}},
			},
			permission: PermissionWriterRun,
		},
		{
			name: "tenant_writer_project_override_viewer_denied_writer_run",
			user: CurrentUser{
				User:          UserSummary{UserID: "user-123"},
				ActiveTenants: []TenantMembershipSummary{{TenantID: "tenant-123", Role: "writer", Status: "active"}},
				ActiveProjects: []ProjectMembershipSummary{{
					TenantID:  "tenant-123",
					ProjectID: "project-123",
					Role:      "viewer",
					Status:    "active",
				}},
			},
			permission: PermissionWriterRun,
		},
		{
			name: "tenant_writer_without_matching_project_denied_writer_run",
			user: CurrentUser{
				User:          UserSummary{UserID: "user-123"},
				ActiveTenants: []TenantMembershipSummary{{TenantID: "tenant-123", Role: "writer", Status: "active"}},
				ActiveProjects: []ProjectMembershipSummary{{
					TenantID:  "tenant-123",
					ProjectID: "other-project",
					Role:      "writer",
					Status:    "active",
				}},
			},
			permission: PermissionWriterRun,
		},
		{
			name:       "resolved_billing_denied_project_read",
			user:       authCurrentUserWithProjectRole("billing"),
			permission: PermissionProjectRead,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(tt.user))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: tt.permission,
			})

			assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
		})
	}
}

func TestReaderBackedAuthorizerLLMModuleBindingManageRequiresTenantAdmin(t *testing.T) {
	for _, role := range []string{"owner", "admin"} {
		t.Run("tenant_"+role, func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithTenantRole(role)))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: PermissionLLMModuleBindingManage,
			})

			if err != nil {
				t.Fatalf("expected tenant role %q to manage LLM module binding: %v", role, err)
			}
		})
	}

	authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(CurrentUser{
		User:          UserSummary{UserID: "user-123"},
		ActiveTenants: []TenantMembershipSummary{{TenantID: "tenant-123", Role: "editor", Status: "active"}},
		ActiveProjects: []ProjectMembershipSummary{{
			TenantID:  "tenant-123",
			ProjectID: "project-123",
			Role:      "project_owner",
			Status:    "active",
		}},
	}))

	err := authorizer.Authorize(context.Background(), AuthorizeInput{
		UserID:     "user-123",
		TenantID:   "tenant-123",
		ProjectID:  "project-123",
		Permission: PermissionLLMModuleBindingManage,
	})

	assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
}

func TestReaderBackedAuthorizerLLMModuleBindingManageAllowsTenantScopeWithoutProject(t *testing.T) {
	authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(authCurrentUserWithTenantRole("admin")))

	err := authorizer.Authorize(context.Background(), AuthorizeInput{
		UserID:     "user-123",
		TenantID:   "tenant-123",
		Permission: PermissionLLMModuleBindingManage,
	})

	if err != nil {
		t.Fatalf("expected tenant-scoped llm management without project id: %v", err)
	}
}

func TestReaderBackedAuthorizerInactiveOrMalformedMembershipStatusesDenyAccess(t *testing.T) {
	tests := []struct {
		name       string
		user       CurrentUser
		permission Permission
	}{
		{
			name:       "blank_project_status_denies_writer_run",
			user:       authCurrentUserWithProjectRoleAndStatus("writer", ""),
			permission: PermissionWriterRun,
		},
		{
			name:       "inactive_project_status_denies_writer_run",
			user:       authCurrentUserWithProjectRoleAndStatus("writer", "inactive"),
			permission: PermissionWriterRun,
		},
		{
			name: "blank_tenant_status_denies_llm_manage",
			user: CurrentUser{
				User:          UserSummary{UserID: "user-123"},
				ActiveTenants: []TenantMembershipSummary{{TenantID: "tenant-123", Role: "owner", Status: ""}},
			},
			permission: PermissionLLMModuleBindingManage,
		},
		{
			name: "inactive_tenant_status_denies_llm_manage",
			user: CurrentUser{
				User:          UserSummary{UserID: "user-123"},
				ActiveTenants: []TenantMembershipSummary{{TenantID: "tenant-123", Role: "admin", Status: "inactive"}},
			},
			permission: PermissionLLMModuleBindingManage,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(tt.user))

			err := authorizer.Authorize(context.Background(), AuthorizeInput{
				UserID:     "user-123",
				TenantID:   "tenant-123",
				ProjectID:  "project-123",
				Permission: tt.permission,
			})

			assertAuthError(t, err, CodeAccessDenied, "current user access is denied")
		})
	}
}

func TestReaderBackedAuthorizerMapsAuthFailuresToStablePublicErrors(t *testing.T) {
	authorizer := NewReaderBackedAuthorizer(staticCurrentUserReader(CurrentUser{}))

	err := authorizer.Authorize(context.Background(), AuthorizeInput{
		TenantID:   "tenant-123",
		ProjectID:  "project-123",
		Permission: PermissionProjectRead,
	})

	assertAuthError(t, err, CodeUnauthenticated, "user context is required")

	authorizer = NewReaderBackedAuthorizer(NewDisabledReader())
	err = authorizer.Authorize(context.Background(), AuthorizeInput{
		UserID:     "user-123",
		TenantID:   "tenant-123",
		ProjectID:  "project-123",
		Permission: PermissionProjectRead,
	})

	assertAuthError(t, err, CodeBackendUnconfigured, "auth reader is not configured")
}

type fakeAuthQueryer struct {
	queries []string
	rows    []SQLRows
	errs    []error
}

func (q *fakeAuthQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	q.queries = append(q.queries, query)
	if len(q.errs) > 0 {
		err := q.errs[0]
		q.errs = q.errs[1:]
		if err != nil {
			return nil, err
		}
	}
	if len(q.rows) == 0 {
		return nil, fmt.Errorf("unexpected query: %s", query)
	}
	rows := q.rows[0]
	q.rows = q.rows[1:]
	return rows, nil
}

type fakeAuthRows struct {
	rows     [][]any
	index    int
	scanErr  error
	err      error
	closeErr error
}

func (r *fakeAuthRows) Next() bool {
	return r.index < len(r.rows)
}

func (r *fakeAuthRows) Scan(dest ...any) error {
	if r.scanErr != nil {
		return r.scanErr
	}
	if r.index >= len(r.rows) {
		return errors.New("scan without row")
	}
	values := r.rows[r.index]
	r.index++
	if len(values) != len(dest) {
		return fmt.Errorf("scan destination count mismatch: got %d want %d", len(dest), len(values))
	}
	for i := range values {
		switch target := dest[i].(type) {
		case *string:
			if values[i] == nil {
				*target = ""
				continue
			}
			value, ok := values[i].(string)
			if !ok {
				return fmt.Errorf("value %d is %T, not string", i, values[i])
			}
			*target = value
		case *sql.NullString:
			if values[i] == nil {
				*target = sql.NullString{}
				continue
			}
			value, ok := values[i].(string)
			if !ok {
				return fmt.Errorf("value %d is %T, not string", i, values[i])
			}
			*target = sql.NullString{String: value, Valid: true}
		default:
			return fmt.Errorf("unsupported scan destination %T", dest[i])
		}
	}
	return nil
}

func (r *fakeAuthRows) Err() error {
	return r.err
}

func (r *fakeAuthRows) Close() error {
	return r.closeErr
}

func assertAuthError(t *testing.T, err error, code string, message string) {
	t.Helper()
	if err == nil {
		t.Fatal("expected error")
	}
	var appErr *AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("expected AppError, got %T: %v", err, err)
	}
	if appErr.Code != code || appErr.Message != message || appErr.Error() != message {
		t.Fatalf("unexpected auth error: %#v", appErr)
	}
}

type staticCurrentUserReader CurrentUser

func (r staticCurrentUserReader) GetCurrentUser(context.Context, GetCurrentUserInput) (CurrentUser, error) {
	return CurrentUser(r), nil
}

func authCurrentUserWithProjectRole(role string) CurrentUser {
	return authCurrentUserWithProjectRoleAndStatus(role, "active")
}

func authCurrentUserWithProjectRoleAndStatus(role string, status string) CurrentUser {
	return CurrentUser{
		User: UserSummary{UserID: "user-123"},
		ActiveProjects: []ProjectMembershipSummary{{
			TenantID:  "tenant-123",
			ProjectID: "project-123",
			Role:      role,
			Status:    status,
		}},
	}
}

func authCurrentUserWithTenantRole(role string) CurrentUser {
	return CurrentUser{
		User:          UserSummary{UserID: "user-123"},
		ActiveTenants: []TenantMembershipSummary{{TenantID: "tenant-123", Role: role, Status: "active"}},
	}
}
