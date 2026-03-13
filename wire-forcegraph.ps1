# ══════════════════════════════════════════════════════════════
#  ASTRA — Wire ForceGraph into project-scoped traceability
#  Run from: C:\Users\Mason\Documents\ASTRA\
#  Usage:  powershell -ExecutionPolicy Bypass -File wire-forcegraph.ps1
# ══════════════════════════════════════════════════════════════

Write-Host "ASTRA ForceGraph Wiring" -ForegroundColor Cyan
Write-Host "=======================" -ForegroundColor Cyan
Write-Host ""

$file = "frontend\src\app\projects\`[id`]\traceability\page.tsx"

if (!(Test-Path -LiteralPath $file)) {
    Write-Host "[MISS] $file not found" -ForegroundColor Red
    exit 1
}

$content = Get-Content -LiteralPath $file -Raw
$changed = $false

# ─────────────────────────────────────────────
# Step 1: Add ForceGraph import after existing imports
# ─────────────────────────────────────────────
$importLine = "import ForceGraph from '@/components/traceability/ForceGraph';"

if (!$content.Contains($importLine)) {
    # Find a good anchor — after the clsx import
    $anchor = "import clsx from 'clsx';"
    if ($content.Contains($anchor)) {
        $content = $content.Replace($anchor, "$anchor`n$importLine")
        $changed = $true
        Write-Host "[FIXED] Added ForceGraph import" -ForegroundColor Green
    } else {
        # Try after any import line containing 'clsx' or 'lucide'
        $anchor2 = "from '@/lib/api';"
        if ($content.Contains($anchor2)) {
            # Insert after the first occurrence
            $idx = $content.IndexOf($anchor2) + $anchor2.Length
            $content = $content.Insert($idx, "`n$importLine")
            $changed = $true
            Write-Host "[FIXED] Added ForceGraph import (after api import)" -ForegroundColor Green
        } else {
            Write-Host "[WARN] Could not find anchor for import insertion. Add manually:" -ForegroundColor Yellow
            Write-Host "       $importLine" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "[SKIP] ForceGraph import already present" -ForegroundColor Yellow
}

# ─────────────────────────────────────────────
# Step 2: Replace the placeholder with ForceGraph
# ─────────────────────────────────────────────

# The placeholder block to find
$placeholder = @'
        <div className="rounded-xl border border-astra-border bg-astra-surface p-8 text-center">
          <GitBranch className="mx-auto mb-3 h-10 w-10 text-slate-600" />
          <h3 className="text-sm font-semibold text-slate-300 mb-1">Interactive Graph View</h3>
          <p className="text-xs text-slate-500">
            {graphData.nodes.length} nodes · {graphData.edges.length} edges
          </p>
          <p className="mt-2 text-[10px] text-slate-600">
            Full D3 force graph available in the original /traceability page. Use Matrix or AI Suggestions for now.
          </p>
        </div>
'@

$replacement = @'
        <div>
          <ForceGraph
            nodes={graphData.nodes}
            edges={graphData.edges}
            onNodeClick={(id) => router.push(`/projects/${projectId}/requirements/${id}`)}
          />
        </div>
'@

if ($content.Contains("Interactive Graph View")) {
    $content = $content.Replace($placeholder, $replacement)
    if ($content.Contains("ForceGraph")) {
        $changed = $true
        Write-Host "[FIXED] Replaced placeholder with ForceGraph component" -ForegroundColor Green
    } else {
        # Fallback: try a simpler match if whitespace differs
        Write-Host "[WARN] Placeholder text found but exact match failed." -ForegroundColor Yellow
        Write-Host "       You may need to manually replace the Graph View placeholder." -ForegroundColor Yellow
        Write-Host "       Replace the placeholder div with:" -ForegroundColor Yellow
        Write-Host ""
        Write-Host $replacement -ForegroundColor White
    }
} else {
    Write-Host "[SKIP] Placeholder not found (ForceGraph may already be wired)" -ForegroundColor Yellow
}

# ─────────────────────────────────────────────
# Step 3: Also fix the empty state for graph view
# ─────────────────────────────────────────────
$oldEmpty = 'graphData.nodes.length === 0 ?'
# This is fine as-is since ForceGraph handles empty state internally

# ─────────────────────────────────────────────
# Save
# ─────────────────────────────────────────────
if ($changed) {
    Set-Content -LiteralPath $file -Value $content -NoNewline
    Write-Host ""
    Write-Host "Done! ForceGraph is wired in." -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "No changes made." -ForegroundColor Yellow
}
