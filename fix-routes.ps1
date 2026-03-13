# ══════════════════════════════════════════════════════════════
#  ASTRA — Fix Legacy Route References
#  Run from: C:\Users\Mason\Documents\ASTRA\
#  Usage:  powershell -ExecutionPolicy Bypass -File fix-routes.ps1
# ══════════════════════════════════════════════════════════════

Write-Host "ASTRA Route Fixer" -ForegroundColor Cyan
Write-Host "=================" -ForegroundColor Cyan
Write-Host ""

$root = "frontend\src\app\projects\`[id`]"

# ─────────────────────────────────────────────
# Fix 1: /projects/[id]/requirements/page.tsx
# ─────────────────────────────────────────────
$file1 = "$root\requirements\page.tsx"
if (Test-Path -LiteralPath $file1) {
    $content = Get-Content -LiteralPath $file1 -Raw
    $old1 = 'const navigateToReq = (id: number) => router.push(`/requirements/${id}`);'
    $new1 = 'const navigateToReq = (id: number) => router.push(`${p}/requirements/${id}`);'
    if ($content.Contains($old1)) {
        $content = $content.Replace($old1, $new1)
        Set-Content -LiteralPath $file1 -Value $content -NoNewline
        Write-Host "[FIXED] requirements/page.tsx - navigateToReq now uses project-scoped route" -ForegroundColor Green
    } else {
        Write-Host "[SKIP]  requirements/page.tsx - pattern not found (already fixed?)" -ForegroundColor Yellow
    }
} else {
    Write-Host "[MISS]  requirements/page.tsx not found" -ForegroundColor Red
}

# ─────────────────────────────────────────────
# Fix 2: /projects/[id]/requirements/[reqId]/page.tsx
# ─────────────────────────────────────────────
$file2 = "$root\requirements\`[reqId`]\page.tsx"
if (Test-Path -LiteralPath $file2) {
    $content = Get-Content -LiteralPath $file2 -Raw
    $changed = $false

    # Fix clone handler
    $old2a = 'router.push(`/requirements/${res.data.id}`)'
    $new2a = 'router.push(`/projects/${projectId}/requirements/${res.data.id}`)'
    if ($content.Contains($old2a)) {
        $content = $content.Replace($old2a, $new2a)
        $changed = $true
        Write-Host "[FIXED] requirements/[reqId]/page.tsx - clone handler" -ForegroundColor Green
    }

    # Fix delete handler back navigation
    $old2b = "router.push('/requirements')"
    $new2b = 'router.push(`/projects/${projectId}/requirements`)'
    if ($content.Contains($old2b)) {
        $content = $content.Replace($old2b, $new2b)
        $changed = $true
        Write-Host "[FIXED] requirements/[reqId]/page.tsx - delete/back navigation" -ForegroundColor Green
    }

    # Fix children links
    $old2d = 'href={`/requirements/${child.id}`}'
    $new2d = 'href={`/projects/${req.project_id}/requirements/${child.id}`}'
    if ($content.Contains($old2d)) {
        $content = $content.Replace($old2d, $new2d)
        $changed = $true
        Write-Host "[FIXED] requirements/[reqId]/page.tsx - children links" -ForegroundColor Green
    }

    if ($changed) {
        Set-Content -LiteralPath $file2 -Value $content -NoNewline
    } else {
        Write-Host "[SKIP]  requirements/[reqId]/page.tsx - no legacy patterns found" -ForegroundColor Yellow
    }
} else {
    Write-Host "[MISS]  requirements/[reqId]/page.tsx not found" -ForegroundColor Red
}

# ─────────────────────────────────────────────
# Fix 3: /projects/[id]/traceability/page.tsx
# ─────────────────────────────────────────────
$file3 = "$root\traceability\page.tsx"
if (Test-Path -LiteralPath $file3) {
    $content = Get-Content -LiteralPath $file3 -Raw
    $old3 = 'router.push(`/requirements/${row.id}`)'
    $new3 = 'router.push(`/projects/${projectId}/requirements/${row.id}`)'
    if ($content.Contains($old3)) {
        $content = $content.Replace($old3, $new3)
        Set-Content -LiteralPath $file3 -Value $content -NoNewline
        Write-Host "[FIXED] traceability/page.tsx - matrix row navigation" -ForegroundColor Green
    } else {
        Write-Host "[SKIP]  traceability/page.tsx - pattern not found" -ForegroundColor Yellow
    }
} else {
    Write-Host "[MISS]  traceability/page.tsx not found" -ForegroundColor Red
}

# ─────────────────────────────────────────────
# Fix 4: /projects/[id]/verification/page.tsx
# ─────────────────────────────────────────────
$file4 = "$root\verification\page.tsx"
if (Test-Path -LiteralPath $file4) {
    $content = Get-Content -LiteralPath $file4 -Raw
    $old4 = 'router.push(`/requirements/${v.requirement_id}`)'
    $new4 = 'router.push(`${p}/requirements/${v.requirement_id}`)'
    if ($content.Contains($old4)) {
        $content = $content.Replace($old4, $new4)
        Set-Content -LiteralPath $file4 -Value $content -NoNewline
        Write-Host "[FIXED] verification/page.tsx - verification row link" -ForegroundColor Green
    } else {
        Write-Host "[SKIP]  verification/page.tsx - pattern not found (may already use project scope)" -ForegroundColor Yellow
    }
} else {
    Write-Host "[MISS]  verification/page.tsx not found" -ForegroundColor Red
}

# ─────────────────────────────────────────────
# Fix 5: Legacy /requirements/new/page.tsx
# ─────────────────────────────────────────────
$file5 = "frontend\src\app\requirements\new\page.tsx"
if (Test-Path -LiteralPath $file5) {
    $content = Get-Content -LiteralPath $file5 -Raw
    $old5 = "router.push('/requirements')"
    $new5 = 'router.push(`/projects/${projectId}/requirements`)'
    if ($content.Contains($old5)) {
        $content = $content.Replace($old5, $new5)
        Set-Content -LiteralPath $file5 -Value $content -NoNewline
        Write-Host "[FIXED] requirements/new/page.tsx - back button" -ForegroundColor Green
    } else {
        Write-Host "[SKIP]  requirements/new/page.tsx - pattern not found" -ForegroundColor Yellow
    }
} else {
    Write-Host "[MISS]  requirements/new/page.tsx not found" -ForegroundColor Red
}

Write-Host ""
Write-Host "Done! Review changes with: git diff" -ForegroundColor Cyan
