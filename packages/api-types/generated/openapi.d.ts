/**
 * GENERATED FILE — DO NOT EDIT BY HAND.
 *
 * Produced by `pnpm api-types:generate` (packages/api-types/scripts/generate.ts)
 * from the FastAPI OpenAPI schema. Re-run after any backend schema change;
 * the api-types-drift CI gate fails if this file is stale.
 */

export interface paths {
  "/health/live": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * Live
     * @description Liveness — process answered. No dependencies.
     */
    get: operations["live_health_live_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/health/ready": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * Ready
     * @description Readiness — DB pool can answer within 2 seconds.
     */
    get: operations["ready_health_ready_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/health": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * Health
     * @description Backward-compat alias of ``/health/live`` for existing pingers.
     */
    get: operations["health_health_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/me": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Me */
    get: operations["me_api_me_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/tenants": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Tenants */
    get: operations["list_tenants_api_tenants_get"];
    put?: never;
    /** Create Tenant */
    post: operations["create_tenant_api_tenants_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/platform/settings": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Read */
    get: operations["read_api_platform_settings_get"];
    /** Update */
    put: operations["update_api_platform_settings_put"];
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/platform/users/invites": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Invites */
    get: operations["list_invites_api_platform_users_invites_get"];
    put?: never;
    /** Create */
    post: operations["create_api_platform_users_invites_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/platform/users/invites/{invite_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post?: never;
    /** Revoke */
    delete: operations["revoke_api_platform_users_invites__invite_id__delete"];
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/platform/roles": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Roles */
    get: operations["list_roles_api_platform_roles_get"];
    put?: never;
    /** Create Role */
    post: operations["create_role_api_platform_roles_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/platform/roles/{role_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Get Role */
    get: operations["get_role_api_platform_roles__role_id__get"];
    put?: never;
    post?: never;
    /** Delete Role */
    delete: operations["delete_role_api_platform_roles__role_id__delete"];
    options?: never;
    head?: never;
    /** Update Role */
    patch: operations["update_role_api_platform_roles__role_id__patch"];
    trace?: never;
  };
  "/api/platform/users/{user_id}/roles": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Grants */
    get: operations["list_grants_api_platform_users__user_id__roles_get"];
    put?: never;
    /** Create Grant */
    post: operations["create_grant_api_platform_users__user_id__roles_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/platform/users/{user_id}/roles/{grant_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post?: never;
    /** Delete Grant */
    delete: operations["delete_grant_api_platform_users__user_id__roles__grant_id__delete"];
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/platform/users": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Users */
    get: operations["list_users_api_platform_users_get"];
    put?: never;
    /** Create User */
    post: operations["create_user_api_platform_users_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/platform/stats": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Get Stats */
    get: operations["get_stats_api_platform_stats_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/platform/audit-log": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Events */
    get: operations["list_events_api_platform_audit_log_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/platform/clients/{slug}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Get Client Detail */
    get: operations["get_client_detail_api_platform_clients__slug__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/permissions/catalog": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Get Catalog */
    get: operations["get_catalog_api_permissions_catalog_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/audit/catalog": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Get Catalog */
    get: operations["get_catalog_api_audit_catalog_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/tenants/{tenant_id}/invites": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Invites */
    get: operations["list_invites_api_tenants__tenant_id__invites_get"];
    put?: never;
    /** Create */
    post: operations["create_api_tenants__tenant_id__invites_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/tenants/{tenant_id}/invites/{invite_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post?: never;
    /** Revoke */
    delete: operations["revoke_api_tenants__tenant_id__invites__invite_id__delete"];
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/signup-status": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Signup Status */
    get: operations["signup_status_api_signup_status_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/signup": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Signup */
    post: operations["signup_api_signup_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/signup/resend": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /**
     * Signup Resend
     * @description Resend the signup-confirmation email.
     *
     *     Gated behind ``signups_enabled`` and rate-limited identically to /signup
     *     (5/IP/hr per-IP PLUS the RL-2 per-email throttle). ALWAYS returns 202
     *     ``confirm_email_sent`` when enabled — there is no oracle revealing whether
     *     the email exists (non-enumeration).
     */
    post: operations["signup_resend_api_signup_resend_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/onboarding/tenants": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Onboard */
    post: operations["onboard_api_onboarding_tenants_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/invites/accept": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Accept */
    post: operations["accept_api_invites_accept_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/workspaces/{workspace_id}/roles": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Roles */
    get: operations["list_roles_api_workspaces__workspace_id__roles_get"];
    put?: never;
    /** Create Role */
    post: operations["create_role_api_workspaces__workspace_id__roles_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/workspaces/{workspace_id}/roles/{role_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Get Role */
    get: operations["get_role_api_workspaces__workspace_id__roles__role_id__get"];
    put?: never;
    post?: never;
    /** Delete Role */
    delete: operations["delete_role_api_workspaces__workspace_id__roles__role_id__delete"];
    options?: never;
    head?: never;
    /** Update Role */
    patch: operations["update_role_api_workspaces__workspace_id__roles__role_id__patch"];
    trace?: never;
  };
  "/api/workspaces/{workspace_id}/members": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Members */
    get: operations["list_members_api_workspaces__workspace_id__members_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/workspaces/{workspace_id}/members/{user_id}/roles": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Grants */
    get: operations["list_grants_api_workspaces__workspace_id__members__user_id__roles_get"];
    put?: never;
    /** Create Grant */
    post: operations["create_grant_api_workspaces__workspace_id__members__user_id__roles_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/workspaces/{workspace_id}/members/{user_id}/roles/{grant_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post?: never;
    /** Delete Grant */
    delete: operations["delete_grant_api_workspaces__workspace_id__members__user_id__roles__grant_id__delete"];
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/workspaces/{workspace_id}/settings": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Get Workspace Settings Route */
    get: operations["get_workspace_settings_route_api_workspaces__workspace_id__settings_get"];
    /** Put Settings */
    put: operations["put_settings_api_workspaces__workspace_id__settings_put"];
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/workspaces/{workspace_id}/audit-log": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Events */
    get: operations["list_events_api_workspaces__workspace_id__audit_log_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/workspaces/{workspace_id}/stats": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Get Stats */
    get: operations["get_stats_api_workspaces__workspace_id__stats_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
}
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    /** AcceptInviteResult */
    AcceptInviteResult: {
      /**
       * Kind
       * @enum {string}
       */
      kind: "platform" | "tenant";
      /** Role */
      role: string;
      /** Tenant Id */
      tenant_id?: string | null;
    };
    /** AuditActionDef */
    AuditActionDef: {
      /** Action */
      action: string;
      /** Label */
      label: string;
      /** Category */
      category: string;
    };
    /** AuditCatalog */
    AuditCatalog: {
      /** Categories */
      categories: components["schemas"]["AuditCategoryDef"][];
      /** Actions */
      actions: components["schemas"]["AuditActionDef"][];
    };
    /** AuditCategoryDef */
    AuditCategoryDef: {
      /** Key */
      key: string;
      /** Label */
      label: string;
    };
    /** AuditEventOut */
    AuditEventOut: {
      /** Id */
      id: number;
      /** Actor Auth User Id */
      actor_auth_user_id: string | null;
      /** Actor Email */
      actor_email: string | null;
      /** Action */
      action: string;
      /** Target Type */
      target_type: string;
      /** Target Id */
      target_id: string;
      /** Scope */
      scope: string;
      /** Workspace Id */
      workspace_id: string | null;
      /** Before */
      before: Record<string, never> | null;
      /** After */
      after: Record<string, never> | null;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /** Action Label */
      readonly action_label: string;
      /** Category */
      readonly category: string;
    };
    /** AuditEventsPage */
    AuditEventsPage: {
      /** Items */
      items: components["schemas"]["AuditEventOut"][];
      /** Next Cursor */
      next_cursor?: string | null;
    };
    /** CreatePlatformInviteRequest */
    CreatePlatformInviteRequest: {
      /**
       * Email
       * Format: email
       */
      email: string;
      role: components["schemas"]["PlatformRole"];
    };
    /** CreateTenantInviteRequest */
    CreateTenantInviteRequest: {
      /**
       * Email
       * Format: email
       */
      email: string;
      role: components["schemas"]["TenantRole"];
    };
    /** CreateTenantRequest */
    CreateTenantRequest: {
      /** Workspace Name */
      workspace_name: string;
    };
    /** CreateTenantResponse */
    CreateTenantResponse: {
      tenant: components["schemas"]["CreatedTenant"];
    };
    /** CreatedTenant */
    CreatedTenant: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Slug */
      slug: string;
      /** Name */
      name: string;
      role: components["schemas"]["TenantRole"];
    };
    /** HTTPValidationError */
    HTTPValidationError: {
      /** Detail */
      detail?: components["schemas"]["ValidationError"][];
    };
    /** MeResponse */
    MeResponse: {
      /**
       * User Id
       * Format: uuid
       */
      user_id: string;
      /**
       * Email
       * Format: email
       */
      email: string;
      platform: components["schemas"]["PlatformContext"] | null;
      /** Platform Permissions */
      platform_permissions: string[];
      /** Tenants */
      tenants: components["schemas"]["TenantContext"][];
      pending_invite: components["schemas"]["PendingInvite"] | null;
    };
    /** PendingInvite */
    PendingInvite: {
      /**
       * Kind
       * @enum {string}
       */
      kind: "platform" | "tenant";
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Tenant Id */
      tenant_id: string | null;
      /** Role */
      role: string;
    };
    /** PermissionDef */
    PermissionDef: {
      /**
       * Scope
       * @enum {string}
       */
      scope: "platform" | "workspace";
      /** Key */
      key: string;
      /** Category */
      category: string;
      /** Description */
      description: string;
    };
    /** PermissionsCatalog */
    PermissionsCatalog: {
      /** Items */
      items: components["schemas"]["PermissionDef"][];
    };
    /**
     * PlatformClientDetail
     * @description A client tenant's info + members for a platform operator.
     *
     *     ``owner_email`` is the email of the tenant's ``owner`` member (the first
     *     membership row with ``role = 'owner'``), or ``None`` if no owner row exists
     *     (e.g. a tenant provisioned but never joined). ``member_count`` is the total
     *     number of ``tenant_memberships`` rows, independent of the inline ``members``
     *     list length (they match today since the list is uncapped, but the field is
     *     explicit so the frontend never has to derive it).
     */
    PlatformClientDetail: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Slug */
      slug: string;
      /** Name */
      name: string;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /** Owner Email */
      owner_email?: string | null;
      /** Member Count */
      member_count: number;
      /** Members */
      members: components["schemas"]["PlatformClientMember"][];
    };
    /**
     * PlatformClientMember
     * @description One member of a client tenant as seen by the platform client-detail view.
     */
    PlatformClientMember: {
      /**
       * Auth User Id
       * Format: uuid
       */
      auth_user_id: string;
      /** Email */
      email: string | null;
      role: components["schemas"]["TenantRole"];
      /**
       * Joined At
       * Format: date-time
       */
      joined_at: string;
    };
    /** PlatformContext */
    PlatformContext: {
      role: components["schemas"]["PlatformRole"];
      /** Is Active */
      is_active: boolean;
    };
    /** PlatformInviteResponse */
    PlatformInviteResponse: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Email
       * Format: email
       */
      email: string;
      role: components["schemas"]["PlatformRole"];
      /**
       * Expires At
       * Format: date-time
       */
      expires_at: string;
      /** Accepted At */
      accepted_at?: string | null;
      /** Revoked At */
      revoked_at?: string | null;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
    };
    /** PlatformInvitesPage */
    PlatformInvitesPage: {
      /** Items */
      items: components["schemas"]["PlatformInviteResponse"][];
      /** Next Cursor */
      next_cursor?: string | null;
    };
    /**
     * PlatformRole
     * @enum {string}
     */
    PlatformRole: "super_admin" | "admin" | "editor";
    /**
     * PlatformRoleGrantIn
     * @description Create-payload for `POST /api/platform/users/{user_id}/roles`.
     */
    PlatformRoleGrantIn: {
      /**
       * Role Id
       * Format: uuid
       */
      role_id: string;
    };
    /** PlatformRoleGrantOut */
    PlatformRoleGrantOut: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Auth User Id
       * Format: uuid
       */
      auth_user_id: string;
      /**
       * Role Id
       * Format: uuid
       */
      role_id: string;
      /** Role Key */
      role_key: string;
      /**
       * Granted At
       * Format: date-time
       */
      granted_at: string;
      /** Granted By */
      granted_by: string | null;
    };
    /** PlatformRoleGrantsPage */
    PlatformRoleGrantsPage: {
      /** Items */
      items: components["schemas"]["PlatformRoleGrantOut"][];
      /** Next Cursor */
      next_cursor?: string | null;
    };
    /**
     * PlatformRoleIn
     * @description Create-payload for a custom platform role.
     */
    PlatformRoleIn: {
      /** Key */
      key: string;
      /** Name */
      name: string;
      /** Description */
      description?: string | null;
      /** Permission Keys */
      permission_keys?: string[];
    };
    /** PlatformRoleOut */
    PlatformRoleOut: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Key */
      key: string;
      /** Name */
      name: string;
      /** Description */
      description: string | null;
      /** Is System */
      is_system: boolean;
      /** Permission Keys */
      permission_keys: string[];
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
    };
    /**
     * PlatformRolePatch
     * @description Partial-update payload. None means 'leave unchanged'.
     */
    PlatformRolePatch: {
      /** Name */
      name?: string | null;
      /** Description */
      description?: string | null;
      /** Permission Keys */
      permission_keys?: string[] | null;
    };
    /** PlatformRolesPage */
    PlatformRolesPage: {
      /** Items */
      items: components["schemas"]["PlatformRoleOut"][];
      /** Next Cursor */
      next_cursor?: string | null;
    };
    /** PlatformSettingsResponse */
    PlatformSettingsResponse: {
      /** Signups Enabled */
      signups_enabled: boolean;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
      /** Updated By Email */
      updated_by_email: string | null;
    };
    /**
     * PlatformStats
     * @description Per-metric platform dashboard counts. ``None`` = not authorized.
     */
    PlatformStats: {
      /** Client Tenants */
      client_tenants?: number | null;
      /** Active Platform Users */
      active_platform_users?: number | null;
      /** Recent Activity */
      recent_activity?: number | null;
    };
    /**
     * PlatformUserCreate
     * @description Direct-create request: email + password + role (``admin`` only).
     */
    PlatformUserCreate: {
      /**
       * Email
       * Format: email
       */
      email: string;
      /** Password */
      password: string;
      /**
       * Role
       * @constant
       * @enum {string}
       */
      role: "admin";
    };
    /**
     * PlatformUserCreated
     * @description The newly provisioned platform user.
     */
    PlatformUserCreated: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Email
       * Format: email
       */
      email: string;
      /**
       * Role
       * @constant
       * @enum {string}
       */
      role: "admin";
      /** Is Active */
      is_active: boolean;
    };
    /**
     * PlatformUserListItemOut
     * @description One platform user as seen by the platform-users list endpoint.
     */
    PlatformUserListItemOut: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Email
       * Format: email
       */
      email: string;
      role: components["schemas"]["PlatformRole"];
      /** Is Active */
      is_active: boolean;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /** Last Sign In At */
      last_sign_in_at: string | null;
      /** Granted Role Count */
      granted_role_count: number;
    };
    /** PlatformUsersPage */
    PlatformUsersPage: {
      /** Items */
      items: components["schemas"]["PlatformUserListItemOut"][];
      /** Next Cursor */
      next_cursor?: string | null;
    };
    /** SignupRequest */
    SignupRequest: {
      /**
       * Email
       * Format: email
       */
      email: string;
      /** Password */
      password: string;
    };
    /** SignupResendRequest */
    SignupResendRequest: {
      /**
       * Email
       * Format: email
       */
      email: string;
    };
    /** SignupResponse */
    SignupResponse: {
      /**
       * State
       * @constant
       * @enum {string}
       */
      state: "confirm_email_sent";
    };
    /** SignupStatus */
    SignupStatus: {
      /** Signups Enabled */
      signups_enabled: boolean;
    };
    /** TenantContext */
    TenantContext: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Slug */
      slug: string;
      /** Name */
      name: string;
      role: components["schemas"]["TenantRole"];
      /** Permissions */
      permissions: string[];
    };
    /** TenantIn */
    TenantIn: {
      /** Slug */
      slug: string;
      /** Name */
      name: string;
    };
    /** TenantInviteResponse */
    TenantInviteResponse: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Tenant Id
       * Format: uuid
       */
      tenant_id: string;
      /**
       * Email
       * Format: email
       */
      email: string;
      role: components["schemas"]["TenantRole"];
      /**
       * Expires At
       * Format: date-time
       */
      expires_at: string;
      /** Accepted At */
      accepted_at?: string | null;
      /** Revoked At */
      revoked_at?: string | null;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
    };
    /** TenantInvitesPage */
    TenantInvitesPage: {
      /** Items */
      items: components["schemas"]["TenantInviteResponse"][];
      /** Next Cursor */
      next_cursor?: string | null;
    };
    /** TenantOut */
    TenantOut: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Slug */
      slug: string;
      /** Name */
      name: string;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
      /**
       * Created By
       * Format: uuid
       */
      created_by: string;
    };
    /**
     * TenantRole
     * @enum {string}
     */
    TenantRole: "owner" | "admin" | "editor" | "read_only";
    /** TenantsPage */
    TenantsPage: {
      /** Items */
      items: components["schemas"]["TenantOut"][];
      /** Next Cursor */
      next_cursor?: string | null;
    };
    /** UpdatePlatformSettingsRequest */
    UpdatePlatformSettingsRequest: {
      /** Signups Enabled */
      signups_enabled: boolean;
    };
    /** ValidationError */
    ValidationError: {
      /** Location */
      loc: (string | number)[];
      /** Message */
      msg: string;
      /** Error Type */
      type: string;
    };
    /**
     * WorkspaceMemberListItemOut
     * @description One workspace member as seen by the workspace-members list endpoint.
     */
    WorkspaceMemberListItemOut: {
      /**
       * User Id
       * Format: uuid
       */
      user_id: string;
      /** Email */
      email: string | null;
      role: components["schemas"]["TenantRole"];
      /**
       * Joined At
       * Format: date-time
       */
      joined_at: string;
      /** Granted Role Count */
      granted_role_count: number;
    };
    /** WorkspaceMembersPage */
    WorkspaceMembersPage: {
      /** Items */
      items: components["schemas"]["WorkspaceMemberListItemOut"][];
      /** Next Cursor */
      next_cursor?: string | null;
    };
    /**
     * WorkspaceRoleGrantIn
     * @description Create-payload for `POST /api/workspaces/{wid}/members/{uid}/roles`.
     */
    WorkspaceRoleGrantIn: {
      /**
       * Role Id
       * Format: uuid
       */
      role_id: string;
    };
    /** WorkspaceRoleGrantOut */
    WorkspaceRoleGrantOut: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Auth User Id
       * Format: uuid
       */
      auth_user_id: string;
      /**
       * Workspace Id
       * Format: uuid
       */
      workspace_id: string;
      /**
       * Role Id
       * Format: uuid
       */
      role_id: string;
      /** Role Key */
      role_key: string;
      /**
       * Granted At
       * Format: date-time
       */
      granted_at: string;
      /** Granted By */
      granted_by: string | null;
    };
    /** WorkspaceRoleGrantsPage */
    WorkspaceRoleGrantsPage: {
      /** Items */
      items: components["schemas"]["WorkspaceRoleGrantOut"][];
      /** Next Cursor */
      next_cursor?: string | null;
    };
    /**
     * WorkspaceRoleIn
     * @description Create-payload for a custom workspace role.
     */
    WorkspaceRoleIn: {
      /** Key */
      key: string;
      /** Name */
      name: string;
      /** Description */
      description?: string | null;
      /** Permission Keys */
      permission_keys?: string[];
    };
    /** WorkspaceRoleOut */
    WorkspaceRoleOut: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Workspace Id
       * Format: uuid
       */
      workspace_id: string;
      /** Key */
      key: string;
      /** Name */
      name: string;
      /** Description */
      description: string | null;
      /** Is System */
      is_system: boolean;
      /** Permission Keys */
      permission_keys: string[];
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
    };
    /**
     * WorkspaceRolePatch
     * @description Partial-update payload. None means 'leave unchanged'.
     */
    WorkspaceRolePatch: {
      /** Name */
      name?: string | null;
      /** Description */
      description?: string | null;
      /** Permission Keys */
      permission_keys?: string[] | null;
    };
    /** WorkspaceRolesPage */
    WorkspaceRolesPage: {
      /** Items */
      items: components["schemas"]["WorkspaceRoleOut"][];
      /** Next Cursor */
      next_cursor?: string | null;
    };
    /**
     * WorkspaceSettingsOut
     * @description Read projection of a tenant row for the settings page.
     */
    WorkspaceSettingsOut: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Slug */
      slug: string;
      /** Name */
      name: string;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
    };
    /**
     * WorkspaceSettingsUpdate
     * @description PUT body — only ``name`` may be changed in P6d.
     */
    WorkspaceSettingsUpdate: {
      /** Name */
      name: string;
    };
    /**
     * WorkspaceStats
     * @description Per-metric workspace dashboard counts. ``None`` = not authorized.
     */
    WorkspaceStats: {
      /** Members */
      members?: number | null;
      /** Pending Invites */
      pending_invites?: number | null;
      /** Recent Activity */
      recent_activity?: number | null;
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
  live_health_live_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": {
            [key: string]: string;
          };
        };
      };
    };
  };
  ready_health_ready_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": {
            [key: string]: string;
          };
        };
      };
    };
  };
  health_health_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": {
            [key: string]: string;
          };
        };
      };
    };
  };
  me_api_me_get: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["MeResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  list_tenants_api_tenants_get: {
    parameters: {
      query?: {
        cursor?: string | null;
        limit?: number;
      };
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["TenantsPage"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  create_tenant_api_tenants_post: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["TenantIn"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["TenantOut"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  read_api_platform_settings_get: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlatformSettingsResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  update_api_platform_settings_put: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["UpdatePlatformSettingsRequest"];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlatformSettingsResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  list_invites_api_platform_users_invites_get: {
    parameters: {
      query?: {
        cursor?: string | null;
        limit?: number;
      };
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlatformInvitesPage"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  create_api_platform_users_invites_post: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["CreatePlatformInviteRequest"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlatformInviteResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  revoke_api_platform_users_invites__invite_id__delete: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        invite_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  list_roles_api_platform_roles_get: {
    parameters: {
      query?: {
        cursor?: string | null;
        limit?: number;
      };
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlatformRolesPage"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  create_role_api_platform_roles_post: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["PlatformRoleIn"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlatformRoleOut"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  get_role_api_platform_roles__role_id__get: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        role_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlatformRoleOut"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  delete_role_api_platform_roles__role_id__delete: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        role_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  update_role_api_platform_roles__role_id__patch: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        role_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["PlatformRolePatch"];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlatformRoleOut"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  list_grants_api_platform_users__user_id__roles_get: {
    parameters: {
      query?: {
        cursor?: string | null;
        limit?: number;
      };
      header?: {
        authorization?: string | null;
      };
      path: {
        user_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlatformRoleGrantsPage"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  create_grant_api_platform_users__user_id__roles_post: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        user_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["PlatformRoleGrantIn"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlatformRoleGrantOut"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  delete_grant_api_platform_users__user_id__roles__grant_id__delete: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        user_id: string;
        grant_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  list_users_api_platform_users_get: {
    parameters: {
      query?: {
        cursor?: string | null;
        limit?: number;
      };
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlatformUsersPage"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  create_user_api_platform_users_post: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["PlatformUserCreate"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlatformUserCreated"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  get_stats_api_platform_stats_get: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlatformStats"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  list_events_api_platform_audit_log_get: {
    parameters: {
      query?: {
        cursor?: string | null;
        limit?: number;
        category?: string | null;
      };
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["AuditEventsPage"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  get_client_detail_api_platform_clients__slug__get: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        slug: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlatformClientDetail"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  get_catalog_api_permissions_catalog_get: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PermissionsCatalog"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  get_catalog_api_audit_catalog_get: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["AuditCatalog"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  list_invites_api_tenants__tenant_id__invites_get: {
    parameters: {
      query?: {
        cursor?: string | null;
        limit?: number;
      };
      header?: {
        authorization?: string | null;
      };
      path: {
        tenant_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["TenantInvitesPage"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  create_api_tenants__tenant_id__invites_post: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        tenant_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["CreateTenantInviteRequest"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["TenantInviteResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  revoke_api_tenants__tenant_id__invites__invite_id__delete: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        tenant_id: string;
        invite_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  signup_status_api_signup_status_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["SignupStatus"];
        };
      };
    };
  };
  signup_api_signup_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["SignupRequest"];
      };
    };
    responses: {
      /** @description Successful Response */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["SignupResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  signup_resend_api_signup_resend_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["SignupResendRequest"];
      };
    };
    responses: {
      /** @description Successful Response */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["SignupResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  onboard_api_onboarding_tenants_post: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["CreateTenantRequest"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["CreateTenantResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  accept_api_invites_accept_post: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["AcceptInviteResult"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  list_roles_api_workspaces__workspace_id__roles_get: {
    parameters: {
      query?: {
        cursor?: string | null;
        limit?: number;
      };
      header?: {
        authorization?: string | null;
      };
      path: {
        workspace_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["WorkspaceRolesPage"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  create_role_api_workspaces__workspace_id__roles_post: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        workspace_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["WorkspaceRoleIn"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["WorkspaceRoleOut"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  get_role_api_workspaces__workspace_id__roles__role_id__get: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        workspace_id: string;
        role_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["WorkspaceRoleOut"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  delete_role_api_workspaces__workspace_id__roles__role_id__delete: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        workspace_id: string;
        role_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  update_role_api_workspaces__workspace_id__roles__role_id__patch: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        workspace_id: string;
        role_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["WorkspaceRolePatch"];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["WorkspaceRoleOut"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  list_members_api_workspaces__workspace_id__members_get: {
    parameters: {
      query?: {
        cursor?: string | null;
        limit?: number;
      };
      header?: {
        authorization?: string | null;
      };
      path: {
        workspace_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["WorkspaceMembersPage"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  list_grants_api_workspaces__workspace_id__members__user_id__roles_get: {
    parameters: {
      query?: {
        cursor?: string | null;
        limit?: number;
      };
      header?: {
        authorization?: string | null;
      };
      path: {
        workspace_id: string;
        user_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["WorkspaceRoleGrantsPage"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  create_grant_api_workspaces__workspace_id__members__user_id__roles_post: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        workspace_id: string;
        user_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["WorkspaceRoleGrantIn"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["WorkspaceRoleGrantOut"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  delete_grant_api_workspaces__workspace_id__members__user_id__roles__grant_id__delete: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        workspace_id: string;
        user_id: string;
        grant_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  get_workspace_settings_route_api_workspaces__workspace_id__settings_get: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        workspace_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["WorkspaceSettingsOut"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  put_settings_api_workspaces__workspace_id__settings_put: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        workspace_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["WorkspaceSettingsUpdate"];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["WorkspaceSettingsOut"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  list_events_api_workspaces__workspace_id__audit_log_get: {
    parameters: {
      query?: {
        cursor?: string | null;
        limit?: number;
        category?: string | null;
      };
      header?: {
        authorization?: string | null;
      };
      path: {
        workspace_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["AuditEventsPage"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  get_stats_api_workspaces__workspace_id__stats_get: {
    parameters: {
      query?: never;
      header?: {
        authorization?: string | null;
      };
      path: {
        workspace_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["WorkspaceStats"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
}
