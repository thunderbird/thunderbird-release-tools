# Check language packs on ATN

`check_langpacks.py` downloads Thunderbird language packs from
[addons.thunderbird.net](https://addons.thunderbird.net) (ATN) and reads the
`brandShortName` from each one's `branding/brand.properties`. Use it to find
locales whose language packs have not yet been updated for a Thunderbird
version.

Ported from a Node script by John Bieling.

## Usage

Run it as a `tb-release` subcommand (see the [repository README](../../README.md)
to install `tb-release`):

```sh
tb-release check-langpacks --list                              # list all available locales
tb-release check-langpacks --locales de                        # one locale, all Thunderbird versions
tb-release check-langpacks --locales de,fr,en-us --version 149 # some locales, ATN default version for one Thunderbird version
tb-release check-langpacks --version 149                       # all locales, ATN default version for one Thunderbird version
tb-release check-langpacks --version 149 --all-versions        # all locales, every version for one Thunderbird version (slow)
```

| Option | Effect |
|---|---|
| `-L`, `--list` | List all available locales |
| `-l`, `--locales` | Comma-separated locales to check |
| `-v`, `--version` | Thunderbird major version to check; required with more than one locale |
| `-a`, `--all-versions` | With `--version`, check every language pack version for it, not just the one ATN offers by default |

With `--version`, it checks the language pack version ATN offers by default for
that Thunderbird version. Add `--all-versions` to check every language pack
version for it, which finds locales with more than one brand. Without
`--version`, it checks every version of each locale.

For each locale it prints each language pack version checked, with its upload
time and `brandShortName`. With `--version` it also prints a summary: the ATN default
version and its brand, and with `--all-versions`, the brands found and whether
there is more than one. When checking several locales, the summary is a table
at the end.

A brand of `FILE MISSING` means the language pack has no `brand.properties`,
`NOT FOUND` means the file has no `brandShortName`, and `DOWNLOAD ERROR` means
the language pack couldn't be downloaded. These aren't counted as brands.

`--all-versions` across every locale downloads a lot of language packs and
takes a while; without it, `--version` downloads one per locale.
