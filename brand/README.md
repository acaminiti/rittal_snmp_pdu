# Brand assets

`rittal.svg` was pulled from the DK 7955.401's own CMC III web UI
(`http://192.168.1.216/img/rittal.svg`) -- it's Rittal's real logo, served
by their own device firmware, not scraped from a third-party source.
`favicon.ico` came from the same UI, kept here for reference only (not used
by Home Assistant).

`custom_integrations/rittal_snmp_pdu/` is laid out exactly as
[home-assistant/brands](https://github.com/home-assistant/brands) expects
for a HACS custom integration:

```
custom_integrations/rittal_snmp_pdu/
  icon.png       256x256, transparent background
  icon@2x.png    512x512
  logo.png       native aspect ratio, 128px tall
  logo@2x.png    native aspect ratio, 256px tall
```

## To publish

Home Assistant does **not** read these from `custom_components/` at
runtime -- it fetches brand icons from brands.home-assistant.io, which is
generated from that repo. To make them show up in HA's UI:

1. Fork https://github.com/home-assistant/brands.
2. Copy this `custom_integrations/rittal_snmp_pdu/` folder into the fork
   at the same path.
3. Open a PR. Community-reviewed; third-party integrations identifying the
   real hardware they control (as this one does) are routinely accepted,
   but using another company's trademarked logo is ultimately their call --
   don't be surprised if a reviewer asks about it.
