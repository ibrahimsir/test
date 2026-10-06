import unittest

from main import as_items, format_report


class ReportFormattingTests(unittest.TestCase):
    def test_single_power_shell_object_is_normalized(self) -> None:
        self.assertEqual(as_items({"DeviceID": "C:"}), [{"DeviceID": "C:"}])

    def test_empty_or_invalid_power_shell_value_is_normalized(self) -> None:
        self.assertEqual(as_items(None), [])
        self.assertEqual(as_items([{"Name": "Device"}, "invalid"]), [{"Name": "Device"}])

    def test_reports_low_disk_space_and_driver_issues(self) -> None:
        report = {
            "computer_name": "TEST-PC",
            "ram": {"total_kb": 1000, "free_kb": 500, "installed_bytes": 1024**3},
            "volumes": [{"DeviceID": "C:", "Size": 100, "FreeSpace": 5}],
            "disk_drives": [{"Model": "Test disk", "Status": "OK"}],
            "physical_disks": [],
            "driver_issues": [
                {
                    "Name": "Problem device",
                    "PNPClass": "Display",
                    "ConfigManagerErrorCode": 10,
                }
            ],
        }

        output = "\n".join(format_report(report))

        self.assertIn("KRİTİK: C: bölümünde boş alan %10'un altında.", output)
        self.assertIn("Windows sorun bildiren 1 aygıt buldu.", output)
        self.assertIn("hata kodu=10", output)

    def test_reports_high_memory_usage(self) -> None:
        report = {
            "ram": {"total_kb": 1000, "free_kb": 100},
            "volumes": [],
            "physical_disks": [],
            "disk_drives": [],
            "driver_issues": [],
        }

        output = "\n".join(format_report(report))

        self.assertIn("KRİTİK: RAM kullanımı %90 veya üzerinde.", output)


if __name__ == "__main__":
    unittest.main()
