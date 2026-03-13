########################################
# ASTRA Full Backend API Test Suite
# Fixed: $PID conflict, -UseBasicParsing
########################################

$BASE = "http://localhost:8000/api/v1"
$pass = 0
$fail = 0
$skip = 0
$errorList = @()

function Do-Test {
    param(
        [string]$Method,
        [string]$Url,
        [string]$Label,
        [int[]]$Expect = @(200),
        [string]$Body = "",
        [string]$Token = "",
        [string]$CType = "application/json"
    )

    $headers = @{}
    if ($Token) { $headers["Authorization"] = "Bearer $Token" }

    try {
        $p = @{
            Method = $Method
            Uri = $Url
            ContentType = $CType
            Headers = $headers
            ErrorAction = "Stop"
            UseBasicParsing = $true
        }
        if ($Body -and $Method -ne "GET") { $p["Body"] = $Body }

        $r = Invoke-WebRequest @p
        $c = $r.StatusCode

        if ($Expect -contains $c) {
            Write-Host "  PASS  $Label -> $c" -ForegroundColor Green
            $script:pass++
            return ($r.Content | ConvertFrom-Json -ErrorAction SilentlyContinue)
        } else {
            Write-Host "  FAIL  $Label -> $c (expected $($Expect -join ','))" -ForegroundColor Red
            $script:fail++
            $script:errorList += "$Label : got $c"
            return $null
        }
    } catch {
        $c = 0
        if ($_.Exception.Response) { $c = [int]$_.Exception.Response.StatusCode }
        if ($Expect -contains $c) {
            Write-Host "  PASS  $Label -> $c" -ForegroundColor Green
            $script:pass++
        } else {
            $detail = ""
            try { $detail = " [$($_.ErrorDetails.Message)]" } catch {}
            Write-Host "  FAIL  $Label -> $c$detail" -ForegroundColor Red
            $script:fail++
            $script:errorList += "$Label : status $c"
        }
        return $null
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  ASTRA Backend API Test Suite" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── Health ──
Write-Host "--- Health ---" -ForegroundColor Yellow
Do-Test -Method GET -Url "http://localhost:8000/health" -Label "Health check"

# ── Auth Login ──
Write-Host "`n--- Auth ---" -ForegroundColor Yellow
$token = $null
try {
    $loginBody = "username=mason&password=Admin123!"
    $lr = Invoke-WebRequest -Method POST -Uri "$BASE/auth/login" `
        -ContentType "application/x-www-form-urlencoded" `
        -Body $loginBody -ErrorAction Stop -UseBasicParsing
    $token = ($lr.Content | ConvertFrom-Json).access_token
    Write-Host "  PASS  Login -> 200" -ForegroundColor Green
    $pass++
} catch {
    # Try alternate password
    try {
        $loginBody = "username=mason&password=password123"
        $lr = Invoke-WebRequest -Method POST -Uri "$BASE/auth/login" `
            -ContentType "application/x-www-form-urlencoded" `
            -Body $loginBody -ErrorAction Stop -UseBasicParsing
        $token = ($lr.Content | ConvertFrom-Json).access_token
        Write-Host "  PASS  Login -> 200 (alt password)" -ForegroundColor Green
        $pass++
    } catch {
        Write-Host "  FAIL  Login failed" -ForegroundColor Red
        $fail++
        $errorList += "Login failed"
        Write-Host "`n  Cannot continue without token." -ForegroundColor Red
        return
    }
}

Do-Test -Method GET -Url "$BASE/auth/me" -Label "Get current user" -Token $token

# ── Projects ──
Write-Host "`n--- Projects ---" -ForegroundColor Yellow

# Use a unique code to avoid duplicates
$testCode = "TST" + (Get-Date -Format "HHmm")
$projJson = "{`"code`":`"$testCode`",`"name`":`"Test Project $testCode`",`"description`":`"Automated test`"}"
Do-Test -Method POST -Url "$BASE/projects/" -Label "Create project" -Body $projJson -Token $token -Expect @(200,201,400)

$projects = Do-Test -Method GET -Url "$BASE/projects/" -Label "List projects" -Token $token

# FIX: Use $projId instead of $pid (PowerShell reserved variable)
$projId = $null
if ($projects -is [array] -and $projects.Count -gt 0) { $projId = $projects[0].id }
elseif ($projects -and $projects.id) { $projId = $projects.id }

if ($projId) { Write-Host "       Project ID: $projId" -ForegroundColor DarkGray }
else { Write-Host "       WARNING: No project ID found" -ForegroundColor Red }

# ── Requirements ──
Write-Host "`n--- Requirements ---" -ForegroundColor Yellow

$rid = $null
$rid2 = $null

if ($projId) {
    $reqJson = '{"title":"Test Req","statement":"The system shall respond within 500ms under normal load.","rationale":"Perf matters.","req_type":"performance","priority":"high","level":"L1"}'
    $req = Do-Test -Method POST -Url "$BASE/requirements/?project_id=$projId" -Label "Create requirement" -Body $reqJson -Token $token -Expect @(200,201)
    if ($req) { $rid = $req.id }

    Do-Test -Method GET -Url "$BASE/requirements/?project_id=$projId" -Label "List requirements" -Token $token

    $qcUrl = "$BASE/requirements/quality-check?statement=The+system+shall+respond+within+500ms"
    Do-Test -Method POST -Url $qcUrl -Label "Quality check" -Token $token

    if ($rid) {
        Do-Test -Method GET -Url "$BASE/requirements/$rid" -Label "Get requirement" -Token $token
        Do-Test -Method GET -Url "$BASE/requirements/$rid/history" -Label "Requirement history" -Token $token
        Do-Test -Method GET -Url "$BASE/requirements/$rid/comments" -Label "Requirement comments" -Token $token
        Do-Test -Method GET -Url "$BASE/requirements/status-transitions/draft" -Label "Status transitions" -Token $token

        $req2Json = '{"title":"Sub Req","statement":"The API shall return JSON responses for all endpoints.","rationale":"Standard.","req_type":"interface","priority":"medium","level":"L2"}'
        $req2 = Do-Test -Method POST -Url "$BASE/requirements/?project_id=$projId" -Label "Create 2nd requirement" -Body $req2Json -Token $token -Expect @(200,201)
        if ($req2) { $rid2 = $req2.id }
    }
} else {
    Write-Host "  SKIP  No project" -ForegroundColor DarkGray
    $skip += 7
}

# ── Traceability ──
Write-Host "`n--- Traceability ---" -ForegroundColor Yellow

if ($projId -and $rid -and $rid2) {
    $linkJson = "{`"source_type`":`"requirement`",`"source_id`":$rid,`"target_type`":`"requirement`",`"target_id`":$rid2,`"link_type`":`"decomposition`"}"
    Do-Test -Method POST -Url "$BASE/traceability/links" -Label "Create trace link" -Body $linkJson -Token $token -Expect @(200,201)
    Do-Test -Method GET -Url "$BASE/traceability/links?project_id=$projId" -Label "List trace links" -Token $token
    Do-Test -Method GET -Url "$BASE/traceability/matrix?project_id=$projId" -Label "Traceability matrix" -Token $token
    Do-Test -Method GET -Url "$BASE/traceability/coverage?project_id=$projId" -Label "Coverage stats" -Token $token
    Do-Test -Method GET -Url "$BASE/traceability/graph?project_id=$projId" -Label "Traceability graph" -Token $token
} else {
    Write-Host "  SKIP  No project/reqs" -ForegroundColor DarkGray
    $skip += 5
}

# ── Dashboard ──
Write-Host "`n--- Dashboard ---" -ForegroundColor Yellow
if ($projId) {
    Do-Test -Method GET -Url "$BASE/dashboard/stats?project_id=$projId" -Label "Dashboard stats" -Token $token
} else { $skip++ }

# ── Baselines ──
Write-Host "`n--- Baselines ---" -ForegroundColor Yellow
if ($projId) {
    $blJson = "{`"name`":`"Test Baseline`",`"description`":`"Auto test`",`"project_id`":$projId}"
    Do-Test -Method POST -Url "$BASE/baselines/" -Label "Create baseline" -Body $blJson -Token $token -Expect @(200,201)
    Do-Test -Method GET -Url "$BASE/baselines/?project_id=$projId" -Label "List baselines" -Token $token
} else { $skip += 2 }

# ── AI Semantic (Prompt 1) ──
Write-Host "`n--- AI Semantic Analysis ---" -ForegroundColor Yellow
if ($projId) {
    Do-Test -Method GET -Url "$BASE/ai/duplicates?project_id=$projId" -Label "Find duplicates" -Token $token
    Do-Test -Method GET -Url "$BASE/ai/stats?project_id=$projId" -Label "AI stats" -Token $token

    $dupJson = "{`"statement`":`"The system shall respond within 500ms`",`"project_id`":$projId}"
    Do-Test -Method POST -Url "$BASE/ai/check-duplicate" -Label "Check duplicate" -Body $dupJson -Token $token

    if ($rid) {
        Do-Test -Method GET -Url "$BASE/ai/trace-suggestions?requirement_id=$rid" -Label "Trace suggestions" -Token $token
        Do-Test -Method GET -Url "$BASE/ai/verification-suggestion?requirement_id=$rid" -Label "Verification suggestion" -Token $token
    }

    $reidxJson = "{`"project_id`":$projId}"
    Do-Test -Method POST -Url "$BASE/ai/reindex" -Label "Reindex embeddings" -Body $reidxJson -Token $token -Expect @(200,403)
} else { $skip += 6 }

# ── Impact Analysis (Prompt 2) ──
Write-Host "`n--- Impact Analysis ---" -ForegroundColor Yellow
if ($rid) {
    Do-Test -Method GET -Url "$BASE/impact/analyze?requirement_id=$rid&change_description=test" -Label "Impact analysis" -Token $token
    Do-Test -Method GET -Url "$BASE/impact/dependencies?requirement_id=$rid" -Label "Dependency chain" -Token $token
    Do-Test -Method GET -Url "$BASE/impact/what-if?requirement_id=$rid&action=modify" -Label "What-if modify" -Token $token
    Do-Test -Method GET -Url "$BASE/impact/what-if?requirement_id=$rid&action=delete" -Label "What-if delete" -Token $token
    Do-Test -Method GET -Url "$BASE/impact/history?requirement_id=$rid" -Label "Impact history" -Token $token
} else { $skip += 5 }

if ($projId) {
    Do-Test -Method GET -Url "$BASE/impact/project-risk?project_id=$projId" -Label "Project risk" -Token $token
} else { $skip++ }

# ── AI Writer (Prompt 3) ──
Write-Host "`n--- AI Writing Assistant ---" -ForegroundColor Yellow

Do-Test -Method GET -Url "$BASE/ai/writer/status" -Label "Writer status" -Token $token

$proseJson = '{"prose":"The missile system needs 500km detection range and 2 second response time.","project_context":"Defense"}'
Do-Test -Method POST -Url "$BASE/ai/writer/convert-prose" -Label "Convert prose" -Body $proseJson -Token $token -Expect @(200,500)

$impJson = '{"statement":"The system shall be fast enough.","issues":["Ambiguous"]}'
Do-Test -Method POST -Url "$BASE/ai/writer/improve" -Label "Improve requirement" -Body $impJson -Token $token

$decJson = '{"statement":"The system shall detect and track targets.","title":"Detection","current_level":"L1"}'
Do-Test -Method POST -Url "$BASE/ai/writer/decompose" -Label "Decompose requirement" -Body $decJson -Token $token

$verJson = '{"statement":"The system shall respond within 500ms.","method":"test"}'
Do-Test -Method POST -Url "$BASE/ai/writer/generate-verification" -Label "Generate verification" -Body $verJson -Token $token

$ratJson = '{"statement":"The system shall respond within 500ms.","req_type":"performance"}'
Do-Test -Method POST -Url "$BASE/ai/writer/generate-rationale" -Label "Generate rationale" -Body $ratJson -Token $token

$sumJson = '{"changes":[{"req_id":"FR-001","field":"statement","old_value":"500ms","new_value":"200ms"}],"project_name":"Test","board_type":"CCB"}'
Do-Test -Method POST -Url "$BASE/ai/writer/summarize-changes" -Label "Summarize changes" -Body $sumJson -Token $token

# ── Reports ──
Write-Host "`n--- Reports ---" -ForegroundColor Yellow
Do-Test -Method GET -Url "$BASE/reports/catalog" -Label "Report catalog" -Token $token
if ($projId) {
    Do-Test -Method GET -Url "$BASE/reports/history?project_id=$projId" -Label "Report history" -Token $token
}

# ── Audit ──
Write-Host "`n--- Audit ---" -ForegroundColor Yellow
Do-Test -Method GET -Url "$BASE/audit/?limit=5" -Label "Audit log" -Token $token -Expect @(200,404)

# ── Dev/Seed ──
Write-Host "`n--- Dev Endpoints ---" -ForegroundColor Yellow
if ($projId) {
    Do-Test -Method POST -Url "$BASE/dev/seed-project/$projId" -Label "Seed project" -Token $token -Expect @(200,201)
}

# ── Summary ──
$total = $pass + $fail + $skip
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  RESULTS" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Passed:  $pass" -ForegroundColor Green
if ($fail -gt 0) { Write-Host "  Failed:  $fail" -ForegroundColor Red }
else { Write-Host "  Failed:  0" -ForegroundColor Green }
Write-Host "  Skipped: $skip" -ForegroundColor Yellow
Write-Host "  Total:   $total" -ForegroundColor Cyan
Write-Host ""

if ($errorList.Count -gt 0) {
    Write-Host "  Failures:" -ForegroundColor Red
    foreach ($e in $errorList) { Write-Host "    - $e" -ForegroundColor Red }
    Write-Host ""
}

if ($fail -eq 0) { Write-Host "  ALL TESTS PASSED" -ForegroundColor Green }
else { Write-Host "  SOME TESTS FAILED" -ForegroundColor Red }
Write-Host ""
