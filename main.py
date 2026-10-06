import json
import logging
import subprocess
import sys
from collections.abc import Mapping
from typing import Any



POWERSHELL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding

$operatingSystem = Get-CimInstance Win32_OperatingSystem
$computerSystem = Get-CimInstance Win32_ComputerSystem
$volumes = @(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
    Select-Object DeviceID, VolumeName, Size, FreeSpace)
$diskDrives = @(Get-CimInstance Win32_DiskDrive |
    Select-Object Model, Status, Size)
$driverIssues = @(Get-CimInstance Win32_PnPEntity -Filter "ConfigManagerErrorCode <> 0" |
    Select-Object Name, PNPClass, ConfigManagerErrorCode)

$physicalDisks = @()
$physicalDiskError = $null
if (Get-Command Get-PhysicalDisk -ErrorAction SilentlyContinue) {
    try {
        $physicalDisks = @(Get-PhysicalDisk |
            Select-Object FriendlyName, MediaType, HealthStatus, OperationalStatus, Size)
    }
    catch {
        $physicalDiskError = $_.Exception.Message
    }
}

[ordered]@{
    computer_name = $computerSystem.Name
    ram = @{
        installed_bytes = $computerSystem.TotalPhysicalMemory
        total_kb = $operatingSystem.TotalVisibleMemorySize
        free_kb = $operatingSystem.FreePhysicalMemory
    }
    volumes = $volumes
    disk_drives = $diskDrives
    physical_disks = $physicalDisks
    physical_disk_error = $physicalDiskError
    driver_issues = $driverIssues
} | ConvertTo-Json -Depth 5 -Compress
"""

LOGGER = logging.getLogger("windows_health_check")


def get_report() -> dict[str, Any]:
    """Collect a read-only system snapshot using Windows PowerShell."""
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                POWERSHELL_SCRIPT,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"PowerShell sorgusu çalıştırılamadı: {error}") from error

    if result.returncode != 0:
        details = result.stderr.strip() or "PowerShell beklenmeyen bir hata döndürdü."
        raise RuntimeError(f"Windows bilgileri alınamadı: {details}")

    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("PowerShell yanıtı geçerli JSON değil.") from error

    if not isinstance(report, dict):
        raise RuntimeError("PowerShell yanıtında beklenen sistem raporu bulunamadı.")
    return report


def as_items(value: object) -> list[dict[str, Any]]:
    """Normalize PowerShell values that may be either an object or an array."""
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def number(value: object) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return None


def display_name(item: Mapping[str, Any], key: str, fallback: str) -> str:
    value = item.get(key)
    return str(value) if value else fallback


def format_report(report: Mapping[str, Any]) -> list[str]:
    lines = [
        f"Sistem sağlık raporu: {display_name(report, 'computer_name', 'Bu bilgisayar')}",
        "-" * 48,
    ]
    findings: list[str] = []

    ram = report.get("ram")
    if isinstance(ram, Mapping):
        total_kb = number(ram.get("total_kb"))
        free_kb = number(ram.get("free_kb"))
        installed_bytes = number(ram.get("installed_bytes"))
        if total_kb and free_kb is not None:
            used_percent = (total_kb - free_kb) / total_kb * 100
            installed_gb = (
                f", takılı {installed_bytes / (1024 ** 3):.1f} GB"
                if installed_bytes is not None
                else ""
            )
            lines.append(
                f"RAM: kullanım %{used_percent:.1f}{installed_gb}"
            )
            if used_percent >= 90:
                findings.append("KRİTİK: RAM kullanımı %90 veya üzerinde.")
            elif used_percent >= 80:
                findings.append("UYARI: RAM kullanımı %80 veya üzerinde.")
        else:
            lines.append("RAM: kullanım bilgisi alınamadı.")
    else:
        lines.append("RAM: kullanım bilgisi alınamadı.")

    volumes = as_items(report.get("volumes"))
    lines.append("Disk bölümleri:")
    if not volumes:
        lines.append("  Yerel disk bölümü bilgisi alınamadı.")
    for volume in volumes:
        drive = display_name(volume, "DeviceID", "Bilinmeyen bölüm")
        size = number(volume.get("Size"))
        free = number(volume.get("FreeSpace"))
        label = volume.get("VolumeName")
        volume_name = f" ({label})" if label else ""
        if size and free is not None:
            free_percent = free / size * 100
            lines.append(
                f"  {drive}{volume_name}: {free / (1024 ** 3):.1f} GB boş "
                f"({free_percent:.1f}%)"
            )
            if free_percent < 10:
                findings.append(f"KRİTİK: {drive} bölümünde boş alan %10'un altında.")
            elif free_percent < 20:
                findings.append(f"UYARI: {drive} bölümünde boş alan %20'nin altında.")
        else:
            lines.append(f"  {drive}{volume_name}: kapasite bilgisi alınamadı.")

    physical_disks = as_items(report.get("physical_disks"))
    lines.append("Fiziksel disk sağlığı:")
    if physical_disks:
        for disk in physical_disks:
            name = display_name(
                disk,
                "FriendlyName",
                display_name(disk, "Model", "Bilinmeyen disk"),
            )
            health = disk.get("HealthStatus")
            operational = disk.get("OperationalStatus")
            lines.append(
                f"  {name}: sağlık={health or 'bilinmiyor'}, "
                f"durum={operational or 'bilinmiyor'}"
            )
            if health and str(health).casefold() not in {"healthy"}:
                findings.append(f"UYARI: {name} disk sağlık durumu: {health}.")
            operational_values = (
                operational if isinstance(operational, list) else [operational]
            )
            if any(
                value
                and str(value).casefold() not in {"ok", "online"}
                for value in operational_values
            ):
                findings.append(f"UYARI: {name} disk çalışma durumu normal değil.")
    else:
        if report.get("physical_disk_error"):
            lines.append("  Ayrıntılı disk sağlığı sorgulanamadı; temel durum gösteriliyor.")
        else:
            lines.append("  Ayrıntılı disk sağlığı bu sistemde kullanılamıyor.")
        for disk in as_items(report.get("disk_drives")):
            name = display_name(disk, "Model", "Bilinmeyen disk")
            status = disk.get("Status") or "bilinmiyor"
            lines.append(f"  {name}: temel durum={status}")
            if str(status).casefold() != "ok":
                findings.append(f"UYARI: {name} disk durumu: {status}.")

    driver_issues = as_items(report.get("driver_issues"))
    lines.append("Aygıt sürücüleri:")
    if driver_issues:
        lines.append(f"  Sorun bildirilen aygıt sayısı: {len(driver_issues)}")
        for issue in driver_issues:
            name = display_name(issue, "Name", "Adı bilinmeyen aygıt")
            device_class = issue.get("PNPClass")
            code = issue.get("ConfigManagerErrorCode")
            details = f", sınıf={device_class}" if device_class else ""
            lines.append(f"  - {name}{details}, hata kodu={code}")
        findings.append(
            f"UYARI: Windows sorun bildiren {len(driver_issues)} aygıt buldu."
        )
    else:
        lines.append("  Windows tarafından sorun bildirilen aygıt yok.")

    lines.append("-" * 48)
    lines.append("Bulgular:")
    lines.extend(f"  - {finding}" for finding in findings)
    if not findings:
        lines.append("  Belirtilen kontrollerde sorun saptanmadı.")
    return lines


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )
    if sys.platform != "win32":
        LOGGER.error("Bu program yalnızca Windows üzerinde çalışır.")
        return 1

    try:
        report = get_report()
    except RuntimeError as error:
        LOGGER.error("%s", error)
        return 1

    for line in format_report(report):
        LOGGER.info("%s", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
