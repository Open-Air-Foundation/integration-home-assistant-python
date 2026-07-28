# AirGradient Local API V1 Integration Specification

## Status

This document is the authoritative implementation plan for supporting the
versioned AirGradient Local API (`/api/v1/...`) in `python-airgradient` and the
Home Assistant AirGradient integration while preserving support for legacy
devices.

AirGradient Go (`P-1PSG`) is the first target product. The client architecture
must remain suitable for other products implementing the common Local API V1
catalog, but Home Assistant must expose only capabilities known to be supported
by the connected model and running firmware.

The firmware component is stable, but the Go product integration remains
experimental until it has been validated with a physical device and an external
client.

## Sources of Truth

The implemented firmware contract takes precedence over historical planning
documents:

- Go integration and lifecycle:
  `airgradient-firmware/products/go/docs/local_server.md`
- Generic Local API component:
  `airgradient-firmware/components/airgradient-local-server/`
- Current Python client: `python-airgradient/src/airgradient/`
- Current Home Assistant integration:
  `homeassistant-core/homeassistant/components/airgradient/`

This document replaces:

- `AIRGRADIENT_V1_API_DECISIONS.md`
- `api-v1-naming-decision.md`
- `AIRGRADIENT_V1_API_IMPLEMENTATION_PLAN.md`

## Scope

### In scope

- Legacy and Local API V1 devices through one `AirGradientClient`.
- Probe-based API selection, with `api=1` as an optional mDNS hint.
- Normalization of both wire formats into common public models.
- All measures currently emitted by AirGradient Go.
- The common V1 config catalog required by the existing client methods,
  including Go support for CO2 ABC and VOC/NOx learning offsets.
- Go-specific timing, GPS, LED, buzzer, and `cloudConnection` config fields.
- Typed parsing of Go correction settings.
- CO2 calibration and LED-test actions on Go.
- Structured Local API V1 errors, including `503 busy`.
- Home Assistant discovery, polling, controls, actions, and diagnostics.
- Explicit model/action capabilities with payload-presence filtering.
- Regression coverage for existing legacy devices.

### Out of scope for the initial integration

- HTTPS, authentication, authorization, or CORS changes in firmware.
- Persisting the detected API version in a Home Assistant config entry.
- Re-detecting or switching API versions during a client's lifetime.
- Ports other than the current Local API port 80.
- Waiting for asynchronous config writes to converge.
- Automatically retrying config writes or actions.
- Home Assistant entities for editing measurement corrections.
- Product-specific endpoints outside the common Local API routes.
- Action progress or completion reporting.

## Agreed Integration Decisions

1. Use one public client facade with private legacy and V1 backends.
2. Detect the API once when each client starts; do not persist the result or
   re-detect it at runtime.
3. Use mDNS `api=1` only as an optimization hint.
4. Keep the existing public client method names and normalized attribute names.
5. Treat legacy config `200` and V1 config `202` as successful admission.
6. Do not poll until a config value is observed. Home Assistant keeps its
   existing post-write refresh and one-minute polling behavior.
7. Home Assistant exposes only `local` and `cloud` as configuration-control
   options. During setup, `both` is changed to `local` as it is today.
8. The library still parses `both`, because it is valid on the wire.
9. Parse corrections in the library and include them in Home Assistant
   diagnostics, but do not create correction entities.
10. Keep measures and config in the existing combined Home Assistant
    coordinator.
11. Keep port 80 fixed for this implementation.
12. Require the `boot` wire field for V1 payloads. For legacy payloads, prefer
    `boot` and accept deprecated `bootCount` as a fallback for older devices.
    Normalize either field to the existing `boot_time` attribute.
13. Enable battery percentage by default. Additional particle counts and
    voltage sensors are disabled by default.

---

## Firmware Contract Used by Clients

### Availability and discovery

AirGradient Go exposes the Local API only after it has obtained an IP address in
Stationary mode. Portable, Offline, and active provisioning modes do not expose
the routes.

The device advertises `_airgradient._tcp` with:

| Property | Go value |
|---|---|
| Hostname | `airgradient_<serial>.local` |
| Port | `80` |
| TXT `vendor` | `AirGradient` |
| TXT `model` | `P-1PSG` |
| TXT `serialno` | Same as measures `serialNumber` |
| TXT `fw_ver` | Same as measures `firmware` |
| TXT `api` | `1` |

The endpoint uses plain HTTP without authentication. Clients must assume the
local network is trusted.

During a transient Wi-Fi disconnect the routes remain registered, but the
device is unreachable until it regains an address. During committed OTA, cached
GET requests can remain available while config writes and actions return `403`.

### Routes and success statuses

| Method | Route | Success |
|---|---|---:|
| `GET` | `/api/v1/measures` | `200` JSON |
| `GET` | `/api/v1/config` | `200` JSON |
| `PUT` | `/api/v1/config` | Empty `202 Accepted` |
| `POST` | `/api/v1/actions/calibrate-co2` | Empty `200` |
| `POST` | `/api/v1/actions/test-leds` | Empty `200` |

Unknown routes, wrong methods, legacy paths on a V1-only device, and trailing
slash variants use the HTTP server's unstructured default `404`. A bare route
`404` must remain distinguishable from a structured Local API error.

### Measures

`GET /api/v1/measures` requires these fields:

| Field | Type | Meaning |
|---|---|---|
| `serialNumber` | string | Device serial number |
| `model` | string | Model identifier; `P-1PSG` on Go |
| `firmware` | string | Firmware version |
| `boot` | integer | Retained uptime in completed minutes on Go |

Optional fields are omitted when unsupported or currently invalid. They are not
emitted as JSON `null`.

| Field | Type | Unit or meaning |
|---|---|---|
| `wifiRssi` | integer | dBm |
| `co2` | integer | ppm |
| `pm01` | number | µg/m³ |
| `pm25` | number | µg/m³ |
| `pm10` | number | µg/m³ |
| `pm003Count` | integer | particles/dL |
| `pm005Count` | integer | particles/dL |
| `pm01Count` | integer | particles/dL |
| `pm02Count` | integer | particles/dL |
| `pm50Count` | integer | particles/dL |
| `pm10Count` | integer | particles/dL |
| `temperature` | number | °C, independent of display unit |
| `humidity` | number | % |
| `tvocIndex` | integer | VOC index |
| `tvocRaw` | integer | raw VOC ticks |
| `noxIndex` | integer | NOx index |
| `noxRaw` | integer | raw NOx ticks |
| `battPercent` | integer | % |
| `battVolt` | number | battery voltage |
| `chargeVolt` | number | input/VBUS voltage |

V1 PM2.5, temperature, and humidity values are already corrected. The V1
backend maps them directly to the normalized presentation attributes and does
not synthesize legacy raw or compensated values.

`chargeVolt` is an input voltage and must not be interpreted as a charging-state
boolean.

### Configuration

`GET /api/v1/config` emits only fields supported by the product. `PUT` accepts a
partial object. Go's complete supported subset is:

| Field | Values |
|---|---|
| `pmStandard` | `ugm3`, `us-aqi` |
| `temperatureUnit` | `c`, `f` |
| `measurementInterval` | integer 1 .. 3600 seconds |
| `gpsMode` | `off`, `tracking`, `always` |
| `frontLedBrightness` | integer 0 .. 3: off, dim, mid, bright |
| `backLedBrightness` | integer 0 .. 3: off, dim, mid, bright |
| `touchLedIntensity` | integer 0 .. 2: off, dim, bright |
| `buzzerEnabled` | boolean |
| `cloudConnection` | boolean |
| `configurationControl` | `cloud`, `local`, `both` |
| `co2AbcDays` | integer `-1` or 1 .. 200; `-1` disables ABC |
| `tvocLearningOffset` | integer 1 .. 1000 hours |
| `noxLearningOffset` | integer 1 .. 1000 hours |
| `corrections` | Correction object |

Known V1 catalog fields that Go does not support are omitted from GET and return
a structured `404 not_found` when written, provided access policy permits the
request to reach capability validation:

- `country`
- `postDataToCloud`
- `ledMode`
- `ledBarBrightness`
- `displayBrightness`
- `mqttBrokerUrl`
- `httpDomain`

Legacy names such as `postDataToAirGradient`, `abcDays`, and `ledBarMode` are not
valid V1 keys.

#### Configuration source policy

| Current value | Local API PUT | Cloud fetch |
|---|---|---|
| `cloud` | Rejected, except an exact source-only change to `local` or `both` | Enabled |
| `local` | Enabled | Disabled |
| `both` | Enabled | Enabled |

A candidate that combines `configurationControl: "cloud"` with
`cloudConnection: false` is invalid and returns `400 invalid_value`.

Home Assistant intentionally preserves its existing simpler UI policy:

- Present only `local` and `cloud` in the select entity.
- Change `both` to `local` during setup.
- Keep the configuration-control select available so a cloud-controlled device
  can be returned to local control.
- Expose all other writable controls and actions only while the normalized
  source is `local`.

This UI policy is stricter than the firmware's action policy and is retained for
compatibility with existing integration behavior.

#### Corrections

The canonical shape is:

```json
{
  "corrections": {
    "pm25": {
      "correctionAlgorithm": "none",
      "slr": null
    },
    "temperature": {
      "correctionAlgorithm": "none",
      "slr": null
    },
    "humidity": {
      "correctionAlgorithm": "none",
      "slr": null
    }
  }
}
```

PM2.5 supports `none`, `epa_2021`, and `custom_via_pm25_raw`. Temperature and
humidity support `none` and `custom`. A custom `slr` contains `intercept` and
`scalingFactor`; PM2.5 also contains `useEpa2021`.

The library must parse this shape into typed nested models. Writing corrections
and providing Home Assistant correction controls are deferred.

### Asynchronous write semantics

A V1 config `202` means the request passed parsing, current policy validation,
product validation, FIFO admission, and event signaling. It does not guarantee
that the update was persisted or activated.

The existing client and Home Assistant behavior remains admission-based:

1. A setter returns after legacy `200` or V1 `202`.
2. The Home Assistant entity requests one coordinator refresh.
3. The normal one-minute coordinator updates continue to reconcile state.
4. The integration does not wait until the requested value appears.
5. The integration does not automatically retry.

Closely spaced Home Assistant refresh requests may be coalesced by the
coordinator debouncer. Number, select, and switch platforms each serialize their
own calls, but calls from separate platforms can overlap. If the Go four-entry
shared config/action FIFO is full, the device returns `503 busy` and the caller
must retry explicitly.

An action `200` likewise means only that the action was admitted. It does not
report calibration start, progress, or completion.

Both registered Go actions use these semantics:

- `calibrate-co2` asynchronously requests CO2 calibration.
- `test-leds` asynchronously requests the product LED test.

Neither action reports execution progress or completion through the Local API.

### Structured errors

V1 handler errors use:

```json
{
  "error": {
    "code": "invalid_value",
    "field": "temperatureUnit",
    "message": "invalid value"
  }
}
```

`field` is optional.

| Status | Codes | Meaning |
|---:|---|---|
| `400` | `invalid_body`, `unknown_field`, `invalid_value` | Invalid request |
| `403` | `forbidden` | Access or source policy rejected the operation |
| `404` | `not_found` | Known config field or action unsupported |
| `503` | `busy` | Request could not be admitted |
| `500` | `internal` | Provider or serialization failure |

---

## `python-airgradient` Design

### Public facade and private backends

`AirGradientClient` remains the only public client. It delegates device-local
operations to one of two private backends:

```text
AirGradientClient
├── _LegacyBackend
└── _V1Backend
```

Each backend owns:

- route and method selection;
- expected success statuses;
- wire-format parsing;
- config key translation;
- action transport; and
- version-specific error handling.

Both return the same public normalized model types. Home Assistant must not
branch on wire field names or endpoint paths.

The external firmware-version lookup remains outside the backend split because
it is a cloud operation independent of the local API version.

### API version model

Add:

```python
class ApiVersion(IntEnum):
    LEGACY = 0
    V1 = 1
```

`AirGradientClient` gains:

- constructor argument `api_version: ApiVersion | None = None`;
- read-only `api_version` property after selection; and
- one `asyncio.Lock` protecting initial detection.

Unknown mDNS `api` values are not pre-seeded and fall back to probing known
routes.

### Initial detection

The API version is not selected until a measures request succeeds and parses.
The first route depends on the hint:

- With `api_version=V1`, try V1 first.
- With `api_version=LEGACY` or no hint, try legacy first.

Detection then follows this sequence:

1. Request the first candidate's measures route.
2. If it succeeds and parses, select that backend and retain the measures
   result.
3. If it returns a bare `404`, request the alternate measures route once.
4. If the alternate succeeds and parses, select it and retain the result.
5. Otherwise raise the mapped connection, HTTP, or parse error.

The retained probe result satisfies the first `get_current_measures()` call and
avoids a duplicate request.

A timeout, DNS failure, connection refusal, or non-`404` HTTP failure on the
first candidate ends detection immediately. An offline device therefore causes
one failed request rather than probes of both API routes.

The lock ensures concurrent first calls share the successful detection result.
After selection, the backend remains fixed for the client's lifetime. A later
measures `404` is surfaced normally and does not probe the alternate API. If a
firmware update changes API routes, Home Assistant must reload or restart the
entry so a new client performs detection again.

### Transport behavior

Refactor the common request layer so each operation supplies its expected
success status:

| Operation | Expected status |
|---|---:|
| Legacy GET/PUT | `200` |
| V1 GET | `200` |
| V1 config PUT | `202` |
| V1 action POST | `200` |

The request timeout must include receiving and reading the response body.
Responses must be released on success and failure. Empty successful responses
must not be parsed as JSON.

The V1 backend parses a structured error only when the response contains a valid
Local API error envelope. Bare and malformed error responses remain generic HTTP
failures so initial detection can distinguish a bare `404`.

Legacy non-`200` behavior remains compatible with the current client and maps to
`AirGradientConnectionError`.

### Exceptions

Add a common V1 HTTP error carrying:

- `status: int`
- `code: str | None`
- `field: str | None`
- `message: str | None`
- response content type and body for diagnostics

Public subclasses:

- `AirGradientBadRequestError` for `400`
- `AirGradientForbiddenError` for `403`
- `AirGradientNotSupportedError` for structured `404`
- `AirGradientBusyError` for `503`
- `AirGradientInternalError` for `500`

Keep:

- `AirGradientConnectionError` for transport failures and legacy compatibility;
- `AirGradientParseError` for successful responses that cannot be normalized.

All public exceptions and `ApiVersion` must be exported from
`airgradient.__init__`.

### Measures normalization

Keep the existing public names to avoid breaking Home Assistant entities and
other library consumers:

| V1 field | Public attribute |
|---|---|
| `serialNumber` | `serial_number` |
| `wifiRssi` | `signal_strength` |
| `boot` | `boot_time` |
| `firmware` | `firmware_version` |
| `model` | `model` |
| `co2` | `rco2` |
| `pm01` | `pm01` |
| `pm25` | `pm02` |
| `pm10` | `pm10` |
| `pm003Count` | `pm003_count` |
| `temperature` | `ambient_temperature` |
| `humidity` | `relative_humidity` |
| `tvocIndex` | `total_volatile_organic_component_index` |
| `tvocRaw` | `raw_total_volatile_organic_component` |
| `noxIndex` | `nitrogen_index` |
| `noxRaw` | `raw_nitrogen` |

Add normalized attributes for:

- `pm005_count`
- `pm01_count`
- `pm02_count`
- `pm50_count`
- `pm10_count`
- `battery_percentage`
- `battery_voltage`
- `charge_voltage`

V1 requires `boot` and maps it to `boot_time`. The legacy parser prefers `boot`
when present and accepts deprecated `bootCount` as a fallback for older devices.
A legacy payload containing neither field is invalid.

Make `signal_strength` optional. PM mass attributes must accept numeric values
with decimal precision.

Legacy parsing keeps its compensated-over-raw post-processing. V1 maps its
already-corrected values directly to the canonical attributes. Consequently,
`raw_pm02` and compensated duplicate attributes remain `None` for V1.

### Config normalization

Make every public `Config` field optional so one type can represent the complete
legacy payload and a product-specific V1 subset.

Keep existing public attributes and add:

- `cloud_connection: bool | None`
- `measurement_interval: int | None`
- `gps_mode: GpsMode | None`
- `front_led_brightness: int | None`
- `back_led_brightness: int | None`
- `touch_led_intensity: int | None`
- `buzzer_enabled: bool | None`
- `corrections: Corrections | None`

Add typed correction models for:

- PM2.5, temperature, and humidity entries;
- correction algorithm;
- nullable SLR parameters;
- `intercept`;
- `scaling_factor`; and
- PM-only `use_epa_2021`.

Add `ConfigurationControl.BOTH = "both"`. Preserve
`ConfigurationControl.NOT_INITIALIZED` as a compatibility alias of `BOTH`, but
new code must use `BOTH`.

Add a public string enum for Go's typed GPS mode:

```python
class GpsMode(StrEnum):
    OFF = "off"
    TRACKING = "tracking"
    ALWAYS = "always"
```

The library forwards integer config values without duplicating firmware range
validation. Invalid ranges remain structured V1 `400 invalid_value` responses.

Separate private legacy and V1 parser models supply the wire aliases and convert
to the public normalized `Config`.

Public `Measures`, `Config`, and correction models are plain normalized
dataclasses without Mashumaro wire serialization methods or alias metadata.
Version-specific aliases and deserialization remain private. Export
`parse_measures_json()` and `parse_config_json()` for callers, including test
fixtures, that need to normalize an isolated payload with an explicit
`ApiVersion`. The explicit version is required because config payloads cannot
always be distinguished by field presence alone.

### Public method routing

| Public method | Legacy | V1 |
|---|---|---|
| `get_current_measures()` | `GET /measures/current` | `GET /api/v1/measures` |
| `get_config()` | `GET /config` | `GET /api/v1/config` |
| `set_pm_standard()` | `pmStandard` | `pmStandard` |
| `set_temperature_unit()` | `temperatureUnit` | `temperatureUnit` |
| `set_configuration_control()` | `configurationControl` | `configurationControl` |
| `set_led_bar_mode()` | `ledBarMode` | `ledMode` |
| `set_display_brightness()` | `displayBrightness` | `displayBrightness` |
| `set_led_bar_brightness()` | `ledBarBrightness` | `ledBarBrightness` |
| `enable_sharing_data()` | `postDataToAirGradient` | `postDataToCloud` |
| `set_co2_automatic_baseline_calibration()` | `abcDays` | `co2AbcDays` |
| `set_nox_learning_offset()` | `noxLearningOffset` | `noxLearningOffset` |
| `set_tvoc_learning_offset()` | `tvocLearningOffset` | `tvocLearningOffset` |
| `set_measurement_interval()` | Unsupported | `measurementInterval` |
| `set_gps_mode()` | Unsupported | `gpsMode` |
| `set_front_led_brightness()` | Unsupported | `frontLedBrightness` |
| `set_back_led_brightness()` | Unsupported | `backLedBrightness` |
| `set_touch_led_intensity()` | Unsupported | `touchLedIntensity` |
| `set_buzzer_enabled()` | Unsupported | `buzzerEnabled` |
| `request_co2_calibration()` | Config request boolean | `POST .../calibrate-co2` |
| `request_led_bar_test()` | Config request boolean | `POST .../test-leds` |

Add `set_cloud_connection(enabled: bool)`. It is a V1 operation and must never
be implemented through legacy `postDataToAirGradient` or V1 `postDataToCloud`,
which have different semantics. The legacy backend raises
`AirGradientNotSupportedError` for this operation.

The six Go-specific setters are V1-only and likewise raise
`AirGradientNotSupportedError` locally when the selected backend is legacy.
`set_gps_mode()` accepts `GpsMode`; the remaining setters accept the normalized
integer or boolean value represented by `Config`.

Go returns `AirGradientNotSupportedError` for remaining generic V1 setters it
does not implement. Home Assistant avoids those requests through capability and
payload-presence gating.

---

## Home Assistant Design

### Config flow

#### Zeroconf

1. Read `model`, `serialno`, `fw_ver`, and `api` defensively.
2. Set the config-entry unique ID from `serialno`.
3. For known `api=1`, construct a V1-seeded client.
4. For missing or unknown `api`, allow the client to probe.
5. Fetch measures so probing can confirm or correct the hint.
6. Verify the measures serial matches the TXT serial.
7. Apply the `3.1.1` minimum-version gate only when the resolved
   `client.api_version` is legacy.
8. On confirmation, fetch config and change `both` to `local`.
9. Store only the host in the config entry, preserving the current fixed-port
   behavior.

#### Manual and reconfigure

1. Construct a client without a version hint.
2. Fetch measures to detect the API and identity.
3. Apply the `3.1.1` minimum only when `client.api_version` is legacy.
4. Use the measures serial for unique-ID and reconfigure identity checks.
5. Fetch config and change `both` to `local`.

Unknown future API TXT values do not bypass compatibility checks by themselves.

### Runtime coordinator

Keep one `AirGradientCoordinator` with a one-minute update interval. Each update
continues to fetch measures and config sequentially into one `AirGradientData`.
A failure in either request makes all coordinator-backed entities unavailable,
matching current behavior.

Every measures response must match the config entry's serial number. A mismatch
is an identity error and must not silently move the entry to another device at a
reused IP address.

Number, select, and switch writes keep their current sequence:

1. Await the library setter.
2. Request one coordinator refresh.

Do not add convergence polling, optimistic state, delayed retry, or a new
cross-platform mutation lock in the initial implementation.

Buttons remain fire-and-forget and do not request a config refresh.

### Model name and capabilities

Add:

```text
P-1PSG -> AirGradient Go
```

Replace model substring checks with explicit prefix-based capabilities. The map
must describe config controls and actions, not merely physical components.

Capability rules:

- Measures are always presence-driven.
- V1 config entities require the normalized config value to be present.
- Legacy config entities use the explicit model map because legacy config does
  not reliably describe capability.
- Actions use the model map because V1 has no action-discovery resource.
- An unknown model can expose recognized measurements and present V1 config
  fields, but no action is assumed.

AirGradient Go capabilities:

- Config: PM standard, temperature unit, measurement interval, GPS mode, front
  and back LED brightness, touch LED intensity, buzzer, cloud connection,
  configuration control, ABC days, VOC/NOx learning offsets, and parsed
  corrections.
- Actions: CO2 calibration and LED test.
- Unsupported: generic LED mode, generic LED-bar brightness, display
  brightness, and post-data control.

Home Assistant additionally applies its existing `LOCAL` state gate to writable
entities and actions other than the always-available configuration-control
select.

### Go entity mapping

#### Existing enabled measurement entities

- CO2
- PM1
- PM2.5, preserving the existing `pm02` unique-ID suffix
- PM10
- PM0.3 particle count
- Temperature
- Humidity
- VOC index
- NOx index

Existing raw VOC, raw NOx, and signal-strength defaults remain unchanged. V1
does not create the legacy raw PM2.5 sensor because `raw_pm02` is absent.

#### New measurement entities

| Attribute | Entity | Default |
|---|---|---|
| `battery_percentage` | Battery percentage | Enabled |
| `pm005_count` | PM0.5 particle count | Disabled |
| `pm01_count` | PM1 particle count | Disabled |
| `pm02_count` | PM2.5 particle count | Disabled |
| `pm50_count` | PM5 particle count | Disabled |
| `pm10_count` | PM10 particle count | Disabled |
| `battery_voltage` | Battery voltage diagnostic | Disabled |
| `charge_voltage` | Input voltage diagnostic | Disabled |

No new uptime entity is created. `boot_time` remains available in library data
and diagnostics.

#### Config entities on Go

- Configuration-control select: always present when the field is available;
  options are `local` and `cloud`.
- PM-standard select and diagnostic sensor: available while local control is
  active for writes; diagnostic state remains presence-gated.
- Temperature-unit select and diagnostic sensor: same behavior.
- Measurement-interval number: 1 .. 3600 seconds.
- GPS-mode select: `off`, `tracking`, and `always`.
- Front-LED-brightness select: `off`, `dim`, `mid`, and `bright`, mapped to
  wire values 0, 1, 2, and 3.
- Back-LED-brightness select: `off`, `dim`, `mid`, and `bright`, mapped to wire
  values 0, 1, 2, and 3.
- Touch-LED-intensity select: `off`, `dim`, and `bright`, mapped to wire values
  0, 1, and 2.
- Buzzer-enabled switch.
- Cloud-connection switch: available while local control is active.
- CO2-ABC select using the existing day choices, except that Go maps the
  disabled option to `-1`; legacy devices retain their existing `0` encoding.
- VOC and NOx learning-offset selects using the existing choices.
- Corrections: diagnostics only.

All controls other than configuration control are available only while local
control is active and only when the corresponding normalized config field is
present. Number entities use integer steps and seconds as their unit.

When `cloudConnection` is false, selecting `cloud` is still submitted to the
device. Do not duplicate the cross-field rule in Home Assistant; surface the
firmware's `400 invalid_value` and leave the current state unchanged.

Do not create legacy post-data, generic LED-mode, generic LED-bar-brightness, or
display-brightness entities for Go. Go's product-specific LED controls use the
separate fields and semantic selects listed above.

#### Actions on Go

- CO2 calibration button while Home Assistant's local-control gate is active.
- LED-test button while Home Assistant's local-control gate is active.
- Preserve the existing `request_led_bar_test()` library method and
  `led_bar_test` Home Assistant entity key/unique-ID suffix even though the V1
  action route uses the broader `test-leds` name.

### Optional config handling

Audit every config `value_fn`, `native_value`, `current_option`, and `is_on`
access. A missing optional field must either prevent entity creation or produce
an unknown state; it must not raise an exception.

For V1, payload presence is also a firmware-version compatibility filter. If an
older V1 firmware omits a known field, Home Assistant must not create an entity
that could send that unsupported key.

### Home Assistant error handling

Map at least these errors to actionable messages:

- `AirGradientConnectionError`: communication failure.
- `AirGradientForbiddenError`: device currently rejects local changes; source
  policy or OTA may be responsible.
- `AirGradientBusyError`: device is busy; retry later.
- `AirGradientNotSupportedError`: operation is unsupported by the device.

Bad-request and internal errors may use the existing unknown-error path but must
retain the server message for diagnostics. No action or config request is
retried automatically.

### Update entity

The update entity continues to use the external firmware service. Before release,
verify that `P-1PSG` serials are registered there. If they are not, suppress the
update entity for Go rather than leaving it permanently unavailable.

---

## Implementation Plan

### Phase A: `python-airgradient`

The library is implemented and released before Home Assistant updates its
dependency.

#### A1. Transport and exceptions

Files:

- `src/airgradient/airgradient.py`
- `src/airgradient/exceptions.py`
- `src/airgradient/__init__.py`

Tasks:

- Allow operation-specific success statuses and POST requests.
- Keep body reads inside the timeout and release responses reliably.
- Add structured V1 HTTP errors, including busy.
- Preserve legacy error behavior.
- Add focused tests for statuses, empty success bodies, error envelopes, and
  transport failures.

#### A2. Public and wire models

Files:

- `src/airgradient/models.py`
- optional private legacy/V1 model modules

Tasks:

- Add `ApiVersion`.
- Make normalized config fields optional.
- Make signal strength optional and widen PM numeric fields where required.
- Add Go particle-count, battery, and voltage attributes.
- Add cloud-connection, Go-specific config attributes, `GpsMode`, and correction
  models.
- Add separate private V1 parsers and conversion functions.
- Keep public normalized models as plain dataclasses and add explicit-version
  JSON parsing helpers for isolated payloads.
- Keep legacy compensated-value behavior unchanged.

#### A3. Backends and detection

Files:

- `src/airgradient/airgradient.py`
- private backend modules as appropriate

Tasks:

- Add `_LegacyBackend` and `_V1Backend`.
- Add initial detection, result reuse, and locking.
- Keep the selected backend fixed for the client lifetime.
- Add exact V1 paths, action IDs, and status handling.

#### A4. Public operations and documentation

Tasks:

- Route all existing getters, setters, and actions through the selected backend.
- Add `set_cloud_connection()`.
- Add typed V1-only setters for measurement interval, GPS mode, front and back
  LED brightness, touch LED intensity, and buzzer state.
- Make V1-only setters raise `AirGradientNotSupportedError` on a selected legacy
  backend.
- Add `P-1PSG` model-name support.
- Document admission semantics, Stationary-only availability, errors, and the
  caller-owned session behavior.
- Extend the opt-in local checkout example with all Go-specific config setters
  and a separate explicit LED-test action flag; preserve read-only defaults.
- Export all new public symbols, including the versioned JSON parsing helpers.

#### A5. Release

- Run the library test and static-check suite.
- Update release notes and package version according to repository policy.
- Publish the library before changing Home Assistant's requirement.

### Phase B: Home Assistant

#### B1. Dependency, discovery, and identity

Files:

- `manifest.json`
- `config_flow.py`
- `__init__.py`
- `coordinator.py`

Tasks:

- Bump the released `airgradient` requirement.
- Parse the API hint and apply the legacy version gate conditionally.
- Support manual V1 setup and reconfiguration.
- Preserve `both` to `local` setup behavior.
- Validate serial identity during discovery and every coordinator update.
- Keep runtime version probing and fixed port 80.

#### B2. Capabilities and entities

Files:

- `const.py`
- `sensor.py`
- `number.py`
- `select.py`
- `switch.py`
- `button.py`

Tasks:

- Add explicit model-prefix capabilities.
- Add Go sensor descriptions and defaults.
- Add the Go measurement-interval number, GPS and LED-level selects, buzzer and
  cloud switches, ABC and learning-offset selects, and both action buttons.
- Map the CO2-ABC disabled option to `-1` for Go while preserving legacy `0`.
- Add `both` to the library enum but not the HA select options.
- Gate V1 config entities by payload presence.
- Keep existing local-only dynamic entity behavior.
- Ensure unsupported Go entities and actions are never created.
- Preserve existing unique IDs for common entities.

#### B3. Diagnostics and errors

Files:

- `diagnostics.py`
- `entity.py`
- `strings.json`
- generated translations

Tasks:

- Include typed corrections through the existing dataclass diagnostics output.
- Add forbidden, busy, and unsupported action messages.
- Regenerate translations.

#### B4. Tests and snapshots

- Add Go measures and config fixtures.
- Parametrize shared behavior across legacy and V1 where practical.
- Add Go snapshots for sensors, selects, switches, buttons, diagnostics, device
  information, and update behavior.
- Preserve all legacy snapshots as regression coverage.

---

## Test Matrix

### Library

#### Legacy regression

- Update legacy measures fixtures to use the canonical `boot` field.
- A payload containing both `boot` and `bootCount` uses `boot`, even when the
  values differ.
- A payload containing only `bootCount` uses it as a legacy fallback.
- A legacy payload containing neither `boot` nor `bootCount` raises a parse
  error.
- Existing config fixtures normalize unchanged.
- Existing setter paths, payloads, and `200` handling remain unchanged.
- Compensated values, including zero, continue to override raw values.
- Session ownership and context-manager behavior remain unchanged.

#### V1 measures

- Full Go payload with every optional field.
- Minimal identity payload without Wi-Fi or sensor values.
- Omitted and later-restored optional fields.
- Zero values for all sensors.
- Decimal PM mass values.
- All particle counts and battery values.
- Correct mapping of `pm25`, `temperature`, and `humidity`.
- V1 raw and compensated duplicates remain absent.
- Missing required identity fields and malformed JSON raise parse errors.

#### V1 config

- Exact complete Go response with all 14 supported top-level fields.
- Partial generic V1 response.
- All three configuration-control values.
- All Go-specific timing, GPS, LED, and buzzer fields, including zero and range
  boundary values.
- `GpsMode` parsing for `off`, `tracking`, and `always`.
- Go support for CO2 ABC and VOC/NOx learning offsets.
- All correction algorithms and nullable/custom SLR shapes.
- Correct parsing of `corrections.temperature`.
- `cloudConnection` remains distinct from data sharing.
- Unknown additive response keys are tolerated.

#### Routing and errors

- Exact methods, paths, payloads, and expected statuses.
- Exact payloads for every Go-specific setter.
- Go-specific setters raise `AirGradientNotSupportedError` after legacy
  selection without sending an unsupported config key.
- Empty `202` config success.
- Empty `200` success for both Go actions, including `test-leds`.
- All structured `400` variants.
- `403`, structured `404`, bare `404`, `503`, and `500`.
- Malformed error envelopes.
- Header and body-read timeouts.

#### Detection

- Legacy detection uses one measures request.
- V1 detection uses legacy `404` then V1 success.
- V1 hint skips the initial legacy request.
- Stale V1 hint falls back to legacy only during initial detection.
- Unknown hint probes normally.
- Concurrent initial calls share one detection sequence.
- Timeout or connection failure on the first candidate does not probe the
  alternate route.
- A measures `404` after selection does not probe or change the backend.
- A new client detects a firmware migration that changed API routes.

### Home Assistant

#### Config flow

- Legacy zeroconf applies the minimum firmware version.
- V1 zeroconf skips the legacy version gate.
- Manual legacy and V1 setup.
- Reconfigure serial mismatch.
- TXT/measures serial mismatch.
- Missing or unknown API hint.
- Stale `api=1` hint that resolves to legacy and still applies the legacy
  firmware gate.
- `both` is submitted as `local` during setup.

#### Coordinator and writes

- Every scheduled update fetches measures and config.
- Accepted config write requests one refresh but does not poll to convergence.
- A stale immediate config response is corrected by a later scheduled update.
- A request for `configurationControl=cloud` while `cloudConnection=false`
  surfaces the firmware validation error.
- Go uses `-1`, rather than legacy `0`, when the CO2-ABC disabled option is
  selected.
- Serial changes at the configured host fail the update.
- Busy, forbidden, unsupported, and transport errors are surfaced correctly.

#### Entity sets

- Existing ONE, Open Air, and DIY entity sets remain unchanged.
- Go creates all supported timing, GPS, LED, buzzer, common config, and action
  entities while omitting unsupported generic controls.
- Go LED-level selects map semantic options to their documented integer values.
- Go creates both the CO2-calibration and LED-test buttons.
- Go battery percentage is enabled.
- New particle counts and voltage sensors are disabled by default.
- V1 config omission suppresses the corresponding entity.
- All optional config access tolerates `None`.
- Unknown models expose measurement fields but no assumed actions.

---

## Rollout and Physical Validation

1. Complete library automated coverage.
2. Validate the library directly against a physical Go in Stationary mode.
3. Release the library.
4. Implement and test the Home Assistant changes against that release.
5. Validate zeroconf and manual setup with a Go and a legacy device on the same
   Home Assistant instance.
6. Confirm config admission and later reconciliation for all Go config entities.
7. Confirm CO2 calibration and LED-test admission from their Home Assistant
   buttons.
8. Validate transient Wi-Fi loss, Stationary exit, and OTA read-only behavior.
9. Confirm Go support in the external firmware-version service.

Suggested repository checks, to be run by the developer according to each
repository's instructions:

- Library: `poetry run pytest` and configured static/pre-commit checks.
- Home Assistant: targeted AirGradient tests, translation generation, and the
  repository's configured lint/static checks.

## Done Criteria

- Legacy devices retain their current public API and Home Assistant behavior.
- AirGradient Go can be discovered and configured manually in Stationary mode.
- API V1 is selected without persisting version state.
- Measures and config normalize into common public models.
- Exact V1 routes, field names, `202`, actions, and errors are supported.
- All supported Go config fields and both Go actions are available through the
  library and capability-gated Home Assistant entities.
- Unsupported generic Go controls and unknown actions are not exposed.
- Corrections are visible in diagnostics but not editable in Home Assistant.
- Config writes preserve the existing admission-and-refresh behavior.
- All library and Home Assistant regression/V1 tests pass.
- Physical Go interoperability and external firmware-version coverage are
  confirmed before declaring the integration complete.
