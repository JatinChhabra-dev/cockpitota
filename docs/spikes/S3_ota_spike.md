# Spike S3 — OTA Rollout (hawkBit + Silent APK Install)

## Question
1. Can an update agent (or host runner) silently install/update APKs on the AAOS instance without user intervention?
2. Can Eclipse hawkBit run in a local container and manage rollout distribution sets via its Management and DDI REST APIs?

## Exit Criteria
- [ ] Verify silent APK installation capability on `AAOS-VAR-A` (using `pm install` / PackageInstaller session)
- [ ] Start Eclipse hawkBit container locally (via Docker Compose)
- [ ] Authenticate against hawkBit Management REST API (`http://localhost:8080/rest/v1`)
- [ ] Create a test Software Module & Distribution Set via API
- [ ] Register `AAOS-VAR-A` as a target vehicle in hawkBit
- [ ] Verify DDI API polling endpoint responds (`/default/controller/v1/{controllerId}`)

## Status: IN PROGRESS

---

## Technical Details

### 1. Silent APK Installation on AAOS
In AAOS emulator builds:
- Shell / privileged apps possess `android.permission.INSTALL_PACKAGES` and `android.permission.DELETE_PACKAGES`.
- Command verification:
  ```powershell
  adb shell pm install -r -d -g /data/local/tmp/test.apk
  ```
  Result must return `Success` without displaying any user confirmation dialog on the cockpit screen.

### 2. hawkBit Management & DDI API
- Management API: `http://localhost:8080/rest/v1/softwaremodules`
- Target registration: `http://localhost:8080/rest/v1/targets`
- DDI (Device Integration): `http://localhost:8080/default/controller/v1/{targetId}`
- Authentication default: `admin` / `admin` (basic auth)
