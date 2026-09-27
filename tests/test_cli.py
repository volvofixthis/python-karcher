import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from click import ClickException
from click.testing import CliRunner
import yaml

from karcher.auth import Session
from karcher.cli import (
    authorize,
    cli,
    load_saved_country,
    load_saved_credentials,
    load_saved_session,
    resolve_login_credentials,
    send_clean_control,
    send_resume_control,
)
from karcher.consts import RechargeControl, RoomCleanControl
from karcher.exception import KarcherHomeTokenExpired


def make_auth_token(user_id: str = "user-id") -> str:
    payload = (
        base64.b64encode(json.dumps({"value": json.dumps({"id": user_id})}).encode())
        .decode()
        .rstrip("=")
    )
    return f"header.{payload}.signature"


class TestCredentialsFile(unittest.TestCase):
    def test_load_saved_credentials_supports_yaml_login_key(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            credentials_path = Path(tmp_dir) / "credentials.yaml"
            credentials_path.write_text(
                yaml.safe_dump({"login": "user@example.com", "password": "secret"})
            )

            credentials = load_saved_credentials(str(credentials_path))

        self.assertEqual(credentials, ("user@example.com", "secret"))

    def test_resolve_login_credentials_allows_partial_override(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            credentials_path = Path(tmp_dir) / "credentials.yaml"
            credentials_path.write_text(
                yaml.safe_dump({"username": "user@example.com", "password": "secret"})
            )

            credentials = resolve_login_credentials(
                "override@example.com", None, str(credentials_path)
            )

        self.assertEqual(credentials, ("override@example.com", "secret"))

    def test_load_saved_credentials_requires_password(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            credentials_path = Path(tmp_dir) / "credentials.yaml"
            credentials_path.write_text(
                yaml.safe_dump({"username": "user@example.com"})
            )

            with self.assertRaises(ClickException):
                load_saved_credentials(str(credentials_path))

    def test_load_saved_credentials_still_supports_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            credentials_path = Path(tmp_dir) / "credentials.json"
            credentials_path.write_text(
                json.dumps({"username": "user@example.com", "password": "secret"})
            )

            credentials = load_saved_credentials(str(credentials_path))

        self.assertEqual(credentials, ("user@example.com", "secret"))

    def test_load_saved_country_supports_country_or_region_keys(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            country_path = Path(tmp_dir) / "country.yaml"
            country_path.write_text(
                yaml.safe_dump(
                    {
                        "username": "user@example.com",
                        "password": "secret",
                        "country": "ru",
                    }
                )
            )
            region_path = Path(tmp_dir) / "region.yaml"
            region_path.write_text(
                yaml.safe_dump(
                    {
                        "username": "user@example.com",
                        "password": "secret",
                        "region": "eu",
                    }
                )
            )

            saved_country = load_saved_country(str(country_path))
            saved_region = load_saved_country(str(region_path))

        self.assertEqual(saved_country, "RU")
        self.assertEqual(saved_region, "EU")


class TestTokenFiles(unittest.TestCase):
    @patch("karcher.cli.click.get_app_dir")
    def test_load_saved_session_migrates_legacy_default_json_file(
        self, mock_get_app_dir
    ):
        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_get_app_dir.return_value = tmp_dir
            legacy_path = Path(tmp_dir) / "tokens.json"
            legacy_path.write_text(
                json.dumps(
                    {
                        "auth_token": make_auth_token(),
                        "mqtt_token": "mqtt-token",
                        "register_id": "register-id",
                    }
                )
            )

            session = load_saved_session()

            migrated_path = Path(tmp_dir) / "tokens.yaml"
            self.assertIsNotNone(session)
            assert session is not None
            self.assertTrue(migrated_path.exists())
            self.assertEqual(session.auth_token, make_auth_token())
            self.assertEqual(session.mqtt_token, "mqtt-token")
            self.assertEqual(session.register_id, "register-id")
            self.assertEqual(
                yaml.safe_load(migrated_path.read_text())["mqtt_token"], "mqtt-token"
            )


class TestAuthorize(unittest.IsolatedAsyncioTestCase):
    async def test_authorize_uses_credentials_file(self):
        kh = Mock()
        session = Session()
        session.register_id = "register-id"
        session.user_id = "user-id"
        session.auth_token = make_auth_token()
        session.mqtt_token = "mqtt-token"
        kh.login = AsyncMock(return_value=session)

        with tempfile.TemporaryDirectory() as tmp_dir:
            credentials_path = Path(tmp_dir) / "credentials.yaml"
            token_path = Path(tmp_dir) / "tokens.yaml"
            credentials_path.write_text(
                yaml.safe_dump({"username": "user@example.com", "password": "secret"})
            )

            logout = await authorize(
                kh,
                None,
                None,
                None,
                token_file=str(token_path),
                credentials_file=str(credentials_path),
            )
            saved_tokens = yaml.safe_load(token_path.read_text())

        self.assertTrue(logout)
        kh.login.assert_awaited_once_with("user@example.com", "secret")
        self.assertEqual(saved_tokens["mqtt_token"], "mqtt-token")


class TestCleanControl(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.kh = Mock()
        self.kh.get_devices = AsyncMock(
            return_value=[SimpleNamespace(device_id="device-id")]
        )
        self.kh.set_room_clean = Mock(return_value={"mode": "room"})
        self.kh.set_zone_clean = Mock(return_value={"mode": "zone"})
        self.kh.recharge = Mock(return_value={"mode": "dock"})

    async def test_pause_routes_by_status(self):
        for status, control, method in [
            (6, RoomCleanControl.PAUSE, self.kh.set_room_clean),
            (7, RoomCleanControl.PAUSE, self.kh.set_zone_clean),
        ]:
            with self.subTest(status=status, control=control):
                self.kh.reset_mock()
                self.kh.get_devices = AsyncMock(
                    return_value=[SimpleNamespace(device_id="device-id")]
                )
                self.kh.get_device_properties.return_value = SimpleNamespace(
                    status=status
                )

                await send_clean_control(
                    self.kh, "device-id", control, qos=1, timeout=3.0
                )

                self.kh.get_device_properties.assert_called_once()
                method.assert_called_once()
                self.assertEqual(method.call_args.kwargs["ctrl_value"], control)
                self.assertEqual(method.call_args.kwargs["qos"], 1)
                if status == 6:
                    self.assertEqual(method.call_args.kwargs["room_ids"], [])
                if status == 7:
                    self.assertEqual(method.call_args.kwargs["timeout"], 3.0)

    async def test_resume_routes_by_status_and_sweep_type(self):
        for status, sweep_type, method in [
            (1, 0, self.kh.recharge),
            (2, 1, self.kh.set_room_clean),
            (2, 3, self.kh.set_zone_clean),
        ]:
            with self.subTest(status=status, sweep_type=sweep_type):
                self.kh.reset_mock()
                self.kh.get_devices = AsyncMock(
                    return_value=[SimpleNamespace(device_id="device-id")]
                )
                self.kh.get_device_properties.return_value = SimpleNamespace(
                    status=status, sweep_type=sweep_type
                )

                await send_resume_control(
                    self.kh, "device-id", qos=1, timeout=3.0
                )

                method.assert_called_once()
                if status == 1:
                    self.assertEqual(method.call_args.args[1], RechargeControl.START)
                else:
                    self.assertEqual(
                        method.call_args.kwargs["ctrl_value"], RoomCleanControl.RESUME
                    )
                    self.assertEqual(method.call_args.kwargs["qos"], 1)
                    if sweep_type == 1:
                        self.assertEqual(method.call_args.kwargs["room_ids"], [])
                    else:
                        self.assertEqual(method.call_args.kwargs["timeout"], 3.0)

    async def test_unknown_device_does_not_call_control(self):
        self.kh.get_devices = AsyncMock(return_value=[])

        with self.assertRaisesRegex(Exception, "Device ID not found"):
            await send_clean_control(
                self.kh, "device-id", RoomCleanControl.PAUSE, qos=0, timeout=5.0
            )

        self.kh.get_device_properties.assert_not_called()
        self.kh.set_room_clean.assert_not_called()
        self.kh.set_zone_clean.assert_not_called()
        self.kh.recharge.assert_not_called()

    async def test_unsupported_pause_status_does_not_call_control(self):
        self.kh.get_device_properties.return_value = SimpleNamespace(
            status=2, sweep_type=1
        )

        with self.assertRaisesRegex(Exception, "does not support pause or resume"):
            await send_clean_control(
                self.kh, "device-id", RoomCleanControl.PAUSE, qos=0, timeout=5.0
            )

        self.kh.set_room_clean.assert_not_called()
        self.kh.set_zone_clean.assert_not_called()

    async def test_unsupported_resume_status_does_not_call_control(self):
        self.kh.get_device_properties.return_value = SimpleNamespace(
            status=6, sweep_type=0
        )

        with self.assertRaisesRegex(Exception, "do not support resume"):
            await send_resume_control(self.kh, "device-id", qos=0, timeout=5.0)

        self.kh.recharge.assert_not_called()
        self.kh.set_room_clean.assert_not_called()
        self.kh.set_zone_clean.assert_not_called()

    async def test_unsupported_resume_sweep_type_does_not_call_control(self):
        self.kh.get_device_properties.return_value = SimpleNamespace(
            status=2, sweep_type=2
        )

        with self.assertRaisesRegex(Exception, "do not support resume"):
            await send_resume_control(self.kh, "device-id", qos=0, timeout=5.0)

        self.kh.recharge.assert_not_called()
        self.kh.set_room_clean.assert_not_called()
        self.kh.set_zone_clean.assert_not_called()

    def test_pause_and_resume_are_available_in_help(self):
        result = CliRunner().invoke(cli, ["--help"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("pause", result.output)
        self.assertIn("resume", result.output)


class TestLoginCommand(unittest.TestCase):
    @patch("karcher.cli.KarcherHome.create", new_callable=AsyncMock)
    def test_devices_command_retries_expired_token_with_credentials_file(
        self, mock_create
    ):
        kh = Mock()
        session = Session()
        session.register_id = "register-id"
        session.user_id = "user-id"
        session.auth_token = make_auth_token()
        session.mqtt_token = "new-mqtt-token"
        kh.login_token = Mock()
        kh.login = AsyncMock(return_value=session)
        kh.get_devices = AsyncMock(side_effect=[KarcherHomeTokenExpired(), []])
        kh.close = AsyncMock()
        mock_create.return_value = kh

        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("tokens.yaml").write_text(
                yaml.safe_dump(
                    {
                        "auth_token": make_auth_token("old-user-id"),
                        "mqtt_token": "old-mqtt-token",
                        "register_id": "old-register-id",
                    }
                )
            )
            Path("credentials.yaml").write_text(
                yaml.safe_dump({"login": "user@example.com", "password": "secret"})
            )

            result = runner.invoke(
                cli,
                [
                    "devices",
                    "--token-file",
                    "tokens.yaml",
                    "--credentials-file",
                    "credentials.yaml",
                ],
            )

            saved_tokens = yaml.safe_load(Path("tokens.yaml").read_text())

        self.assertEqual(result.exit_code, 0, result.output)
        kh.login_token.assert_called_once_with(
            make_auth_token("old-user-id"), "old-mqtt-token"
        )
        kh.login.assert_awaited_once_with("user@example.com", "secret")
        kh.close.assert_awaited_once()
        self.assertEqual(saved_tokens["auth_token"], make_auth_token())
        self.assertEqual(saved_tokens["mqtt_token"], "new-mqtt-token")

    @patch("karcher.cli.KarcherHome.create", new_callable=AsyncMock)
    def test_login_command_uses_country_from_credentials_file(self, mock_create):
        kh = AsyncMock()
        session = Session()
        session.register_id = ""
        session.user_id = "user-id"
        session.auth_token = "auth-token"
        session.mqtt_token = "mqtt-token"
        kh.login = AsyncMock(return_value=session)
        kh.close = AsyncMock()
        mock_create.return_value = kh

        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("credentials.yaml").write_text(
                yaml.safe_dump(
                    {
                        "login": "user@example.com",
                        "password": "secret",
                        "country": "ru",
                    }
                )
            )

            result = runner.invoke(
                cli, ["login", "--credentials-file", "credentials.yaml"]
            )

        self.assertEqual(result.exit_code, 0, result.output)
        mock_create.assert_awaited_once_with(country="RU")
        kh.login.assert_awaited_once_with("user@example.com", "secret")

    @patch("karcher.cli.KarcherHome.create", new_callable=AsyncMock)
    def test_login_command_country_option_overrides_credentials_file(self, mock_create):
        kh = AsyncMock()
        session = Session()
        session.register_id = ""
        session.user_id = "user-id"
        session.auth_token = "auth-token"
        session.mqtt_token = "mqtt-token"
        kh.login = AsyncMock(return_value=session)
        kh.close = AsyncMock()
        mock_create.return_value = kh

        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("credentials.yaml").write_text(
                yaml.safe_dump(
                    {
                        "login": "user@example.com",
                        "password": "secret",
                        "country": "ru",
                    }
                )
            )

            result = runner.invoke(
                cli,
                [
                    "--country",
                    "GB",
                    "login",
                    "--credentials-file",
                    "credentials.yaml",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        mock_create.assert_awaited_once_with(country="GB")

    @patch("karcher.cli.KarcherHome.create", new_callable=AsyncMock)
    def test_login_command_accepts_credentials_file(self, mock_create):
        kh = AsyncMock()
        session = Session()
        session.register_id = ""
        session.user_id = "user-id"
        session.auth_token = "auth-token"
        session.mqtt_token = "mqtt-token"
        kh.login = AsyncMock(return_value=session)
        kh.close = AsyncMock()
        mock_create.return_value = kh

        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("credentials.yaml").write_text(
                yaml.safe_dump({"login": "user@example.com", "password": "secret"})
            )

            result = runner.invoke(
                cli, ["login", "--credentials-file", "credentials.yaml"]
            )

        self.assertEqual(result.exit_code, 0, result.output)
        kh.login.assert_awaited_once_with("user@example.com", "secret")
        kh.close.assert_awaited_once()
