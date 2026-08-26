# Kärcher Home Robots client

Python library and cli to authorize into Karcher Home Robots account and fetch device information.

## Usage

To download `karcher-home` cli run:

```sh
pip3 install karcher-home
```

### From console

```console
Usage: karcher-home [OPTIONS] COMMAND [ARGS]...

  Tool for connectiong and getting information from Kärcher Home Robots.

Options:
  -d, --debug                     Enable debug mode.
  -o, --output [json|json_pretty]
                                  Output format. Default: "json"
  -r, --region [eu|us|cn]         Region of the server to query. Default: "eu"
  --help                          Show this message and exit.

Commands:
  dock               Send the device back to the dock.
  device-properties  Get device properties.
  devices            List all devices.
  login              Get user session tokens.
  mqtt-publish       Publish an MQTT message.
  recharge           Start or stop device recharging.
  set-direction      Send a manual direction command.
  set-zone-clean     Start or pause zone cleaning.
  set-room-clean     Start cleaning selected rooms.
  set-zone-points    Set zone points on the current map.
  split-room         Split a room on the current map.
  urls               Get region information.
```

Save tokens once and reuse them later:

```sh
karcher-home login -u "user@email" -p "password"
karcher-home devices
karcher-home dock -d "DEVICE_ID"
```

You can also read login credentials from a YAML file:

```yaml
username: user@email
password: password
country: RU
```

You can also use `region` instead of `country`. When present, the credentials file region is used automatically unless you explicitly pass `--country` on the command line.

Then pass it with `--credentials-file` to `login` or any command that accepts username/password authentication:

```sh
karcher-home login --credentials-file ./credentials.yaml
karcher-home devices --credentials-file ./credentials.yaml
```

Tokens are saved automatically after a successful password-based login, using `tokens.yaml` in the app config directory by default. Existing default `tokens.json` files are migrated automatically the next time they are read. You can override the token path with `--token-file`.

### From code

```python
from karcher.karcher import KarcherHome

kh = await KarcherHome.create()
await kh.login("user@email", "password")
devices = await hk.get_devices()
```

## License

Distributed under the MIT License. See `LICENSE` for more information.
