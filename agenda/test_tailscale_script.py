"""Pruebas est?ticas del configurador privado de Tailscale."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class TailscaleConfigurationScriptTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.script_path = (
            Path(settings.BASE_DIR)
            / "scripts"
            / "configurar_tailscale.ps1"
        )
        cls.script = cls.script_path.read_text(encoding="utf-8")

    def test_script_exists(self):
        self.assertTrue(self.script_path.is_file())

    def test_script_obtains_tailscale_ip_dynamically(self):
        self.assertIn("tailscale.exe", self.script)
        self.assertIn("ip -4", self.script)
        self.assertNotIn("100.121.155.5", self.script)

    def test_script_validates_private_tailscale_range(self):
        self.assertIn(
            r"^100\.",
            self.script,
        )
        self.assertIn(
            "La direcci?n obtenida no parece pertenecer",
            self.script,
        )

    def test_script_obtains_private_dns_name(self):
        self.assertIn("status --json", self.script)
        self.assertIn("Self.DNSName", self.script)
        self.assertIn('TrimEnd(".")', self.script)

    def test_script_configures_csrf_origin(self):
        self.assertIn(
            "AGENDE_CSRF_TRUSTED_ORIGINS",
            self.script,
        )
        self.assertIn(
            '$tailscaleOrigin = "https://$tailscaleDnsName"',
            self.script,
        )

    def test_script_creates_environment_backup(self):
        self.assertIn("Copy-Item", self.script)
        self.assertIn(".backup-$timestamp", self.script)

    def test_script_preserves_local_hosts(self):
        self.assertIn("AGENDE_ALLOWED_HOSTS", self.script)
        self.assertIn('"127.0.0.1"', self.script)
        self.assertIn('"localhost"', self.script)
        self.assertIn("Get-IPv4Addresses", self.script)

    def test_script_does_not_open_firewall_or_router_ports(self):
        forbidden_commands = (
            "New-NetFirewallRule",
            "Set-NetFirewallProfile",
            "netsh advfirewall",
            "tailscale funnel",
            "tailscale serve",
            "Add-NetRoute",
        )

        for command in forbidden_commands:
            with self.subTest(command=command):
                self.assertNotIn(command, self.script)
