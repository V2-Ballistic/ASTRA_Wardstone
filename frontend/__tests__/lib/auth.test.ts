/**
 * ASTRA — Auth / RBAC Utility Tests
 * ===================================
 * File: frontend/__tests__/lib/auth.test.ts
 *
 * Tests the pure hasPermission / permissionsForRole / rolesWithPermission
 * utilities exported from auth.ts.  These mirror the backend permission
 * matrix so the UI can hide/show controls without an API call.
 */

import {
  hasPermission,
  permissionsForRole,
  rolesWithPermission,
} from "../../src/lib/auth";

describe("hasPermission", () => {
  it("admin has all permissions", () => {
    expect(hasPermission("requirements.create", "admin")).toBe(true);
    expect(hasPermission("users.manage", "admin")).toBe(true);
    expect(hasPermission("settings.manage", "admin")).toBe(true);
  });

  it("project_manager has most but not users.manage", () => {
    expect(hasPermission("requirements.create", "project_manager")).toBe(true);
    expect(hasPermission("baselines.create", "project_manager")).toBe(true);
    expect(hasPermission("users.manage", "project_manager")).toBe(false);
  });

  it("requirements_engineer can create and update but not delete", () => {
    expect(hasPermission("requirements.create", "requirements_engineer")).toBe(true);
    expect(hasPermission("requirements.update", "requirements_engineer")).toBe(true);
    expect(hasPermission("requirements.delete", "requirements_engineer")).toBe(false);
  });

  it("reviewer can only approve", () => {
    expect(hasPermission("requirements.approve", "reviewer")).toBe(true);
    expect(hasPermission("requirements.create", "reviewer")).toBe(false);
    expect(hasPermission("requirements.delete", "reviewer")).toBe(false);
  });

  it("stakeholder has no write permissions", () => {
    expect(hasPermission("requirements.create", "stakeholder")).toBe(false);
    expect(hasPermission("requirements.update", "stakeholder")).toBe(false);
    expect(hasPermission("baselines.create", "stakeholder")).toBe(false);
  });

  it("developer has no write permissions", () => {
    expect(hasPermission("requirements.create", "developer")).toBe(false);
    expect(hasPermission("requirements.delete", "developer")).toBe(false);
  });

  it("returns false for null / undefined role", () => {
    expect(hasPermission("requirements.create", null)).toBe(false);
    expect(hasPermission("requirements.create", undefined)).toBe(false);
  });

  it("returns false for unknown role", () => {
    expect(hasPermission("requirements.create", "alien")).toBe(false);
  });
});

describe("permissionsForRole", () => {
  it("returns all admin permissions", () => {
    const perms = permissionsForRole("admin");
    expect(perms).toContain("users.manage");
    expect(perms).toContain("settings.manage");
    expect(perms.length).toBeGreaterThan(10);
  });

  it("returns empty array for unknown role", () => {
    expect(permissionsForRole("alien")).toEqual([]);
  });
});

describe("rolesWithPermission", () => {
  it("users.manage is admin-only", () => {
    const roles = rolesWithPermission("users.manage");
    expect(roles).toContain("admin");
    expect(roles).not.toContain("project_manager");
    expect(roles.length).toBe(1);
  });

  it("requirements.create includes admin, pm, engineer", () => {
    const roles = rolesWithPermission("requirements.create");
    expect(roles).toContain("admin");
    expect(roles).toContain("project_manager");
    expect(roles).toContain("requirements_engineer");
    expect(roles).not.toContain("reviewer");
  });
});
