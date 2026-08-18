@echo off
REM ============================================================
REM  M01 - Resume Ingestion & Claim Extraction, on its own.
REM
REM  This module's services only (PORTS.txt: API 8101).
REM  No sibling repos, so the API answers in its degraded state
REM  and /v1/deps names the module it would have used - which is
REM  the fastest way to check that degradation still works.
REM
REM  Usage:  start_resume.bat          launch M01
REM          start_resume.bat -Check   verify prerequisites only
REM ============================================================

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch.ps1" -Only m01 -Title "M01 - Resume Ingestion" %*
