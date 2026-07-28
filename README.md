# Python: AirGradient

[![GitHub Release][releases-shield]][releases]
[![Python Versions][python-versions-shield]][pypi]
![Project Stage][project-stage-shield]
![Project Maintenance][maintenance-shield]
[![License][license-shield]](LICENSE.md)

[![Build Status][build-shield]][build]
[![Code Coverage][codecov-shield]][codecov]

Asynchronous Python client for the legacy and versioned AirGradient Local APIs.

## About

This package allows you to fetch data from AirGradient.

## Installation

```bash
pip install airgradient
```

## Usage

```python
import asyncio

from airgradient import AirGradientClient


async def main() -> None:
    """Show example of fetching measurement."""
    async with AirGradientClient("10.0.0.123") as client:
        measurements = await client.get_current_measures()
        print(measurements)


if __name__ == "__main__":
    asyncio.run(main())
```

The client probes the Local API once, when the first device operation is made.
An optional `ApiVersion` hint changes which route is tried first, but the
version is selected only after a measures response succeeds and parses. The
selected version is available through the read-only `api_version` property and
does not change for that client instance.

```python
from airgradient import AirGradientClient, ApiVersion

client = AirGradientClient("10.0.0.123", api_version=ApiVersion.V1)
```

Public measures, config, and correction models are normalized plain dataclasses.
To normalize a raw payload whose Local API version is already known, use the
versioned parsing helpers:

```python
from airgradient import ApiVersion, parse_config_json, parse_measures_json

measures = parse_measures_json(payload, api_version=ApiVersion.V1)
config = parse_config_json(config_payload, api_version=ApiVersion.V1)
```

The API version is required because isolated config payloads cannot always be
distinguished by their fields. Public normalized models do not expose wire
serialization methods such as `from_json()` or `to_json()`.

Configuration setters return when the device admits the request: legacy
devices respond with `200`, while V1 devices respond with `202`. Admission does
not guarantee that an asynchronous update has already been persisted or
activated. The library does not retry busy requests or poll for convergence.
Callers should handle `AirGradientBusyError`, `AirGradientForbiddenError`, and
`AirGradientNotSupportedError` as appropriate.

When a caller provides an `aiohttp.ClientSession`, the caller retains ownership
and must close it. A session created internally by `AirGradientClient` is closed
by `close()` or on async context-manager exit.

### Local checkout example

`poetry install` installs the checkout into its virtual environment, so scripts
in other repository folders can import `AirGradientClient` normally when run
through `poetry run`.

Read a device by IP address:

```bash
poetry run python examples/read_local_api.py --ip 192.168.1.123
```

Or build its mDNS hostname from the serial number:

```bash
poetry run python examples/read_local_api.py --serial 84fce612f5b8
```

The serial form connects to `airgradient_<serial>.local`, verifies that the
returned measures serial matches, and prints the detected API version,
normalized measures, and normalized config. Without `--put-config`,
`--calibrate-co2`, or `--test-leds`, it performs only read requests.

Config writes are disabled by default. Enable them explicitly with
`--put-config` and one or more typed config options:

```bash
poetry run python examples/read_local_api.py \
  --serial 84fce612f5b8 \
  --put-config \
  --pm-standard ugm3 \
  --temperature-unit c
```

Boolean options support positive and negative forms, for example
`--cloud-connection` and `--no-cloud-connection`. Each supplied value is sent
as a separate partial config request through the public client setter. The
printed post-write config is an immediate refresh and may still show the old
value because V1 config updates are asynchronous.

Go-specific options include the measurement interval, GPS mode, front and back
LED brightness, touch LED intensity, and buzzer state. For example:

```bash
poetry run python examples/read_local_api.py \
  --serial 84fce612f5b8 \
  --put-config \
  --measurement-interval 30 \
  --gps-mode tracking \
  --buzzer-enabled
```

CO2 calibration is also disabled by default and requires an explicit flag:

```bash
poetry run python examples/read_local_api.py \
  --serial 84fce612f5b8 \
  --calibrate-co2
```

This submits a real calibration request through
`AirGradientClient.request_co2_calibration()`.

The LED test is similarly opt-in:

```bash
poetry run python examples/read_local_api.py \
  --serial 84fce612f5b8 \
  --test-leds
```

This submits a real LED-test request through
`AirGradientClient.request_led_bar_test()`.

## Changelog & Releases

This repository keeps a change log using [GitHub's releases][releases]
functionality. The format of the log is based on
[Keep a Changelog][keepchangelog].

Releases are based on [Semantic Versioning][semver], and use the format
of ``MAJOR.MINOR.PATCH``. In a nutshell, the version will be incremented
based on the following:

- ``MAJOR``: Incompatible or major changes.
- ``MINOR``: Backwards-compatible new features and enhancements.
- ``PATCH``: Backwards-compatible bugfixes and package updates.

## Contributing

This is an active open-source project. We are always open to people who want to
use the code or contribute to it.

We've set up a separate document for our
[contribution guidelines](.github/CONTRIBUTING.md).

Thank you for being involved! :heart_eyes:

## Setting up development environment

This Python project is fully managed using the [Poetry][poetry] dependency manager. But also relies on the use of NodeJS for certain checks during development.

You need at least:

- Python 3.11+
- [Poetry][poetry-install]
- NodeJS 12+ (including NPM)

To install all packages, including all development requirements:

```bash
npm install
poetry install
```

As this repository uses the [pre-commit][pre-commit] framework, all changes
are linted and tested with each commit. You can run all checks and tests
manually, using the following command:

```bash
poetry run pre-commit run --all-files
```

To run just the Python tests:

```bash
poetry run pytest
```

## Authors & contributors

The content is by [Joost Lekkerkerker][joostlek].

For a full list of all authors and contributors,
check [the contributor's page][contributors].

## License

MIT License

Copyright (c) 2024 AirGradient

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

[build-shield]: https://github.com/airgradienthq/python-airgradient/actions/workflows/tests.yaml/badge.svg
[build]: https://github.com/airgradienthq/python-airgradient/actions
[codecov-shield]: https://codecov.io/gh/airgradienthq/python-airgradient/branch/master/graph/badge.svg
[codecov]: https://codecov.io/gh/airgradienthq/python-airgradient
[commits-shield]: https://img.shields.io/github/commit-activity/y/airgradienthq/python-airgradient.svg
[commits]: https://github.com/airgradienthq/python-airgradient/commits/master
[contributors]: https://github.com/airgradienthq/python-airgradient/graphs/contributors
[joostlek]: https://github.com/joostlek
[keepchangelog]: http://keepachangelog.com/en/1.0.0/
[license-shield]: https://img.shields.io/github/license/airgradienthq/python-airgradient.svg
[maintenance-shield]: https://img.shields.io/maintenance/yes/2025.svg
[poetry-install]: https://python-poetry.org/docs/#installation
[poetry]: https://python-poetry.org
[pre-commit]: https://pre-commit.com/
[project-stage-shield]: https://img.shields.io/badge/project%20stage-stable-green.svg
[python-versions-shield]: https://img.shields.io/pypi/pyversions/airgradient
[releases-shield]: https://img.shields.io/github/release/airgradienthq/python-airgradient.svg
[releases]: https://github.com/airgradienthq/python-airgradient/releases
[semver]: http://semver.org/spec/v2.0.0.html
[pypi]: https://pypi.org/project/airgradient/
