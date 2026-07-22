# Third-party notices

## sing-box

`tunnelgram` can start an unmodified `sing-box` command-line executable as a separate process to provide the local mixed HTTP/SOCKS proxy and the HTTP, SOCKS, VLESS and Hysteria2 outbound implementations.

- Project: SagerNet/sing-box
- Website: https://sing-box.sagernet.org/
- Source code: https://github.com/SagerNet/sing-box
- Version bundled by the release workflows: `1.13.14`
- Exact source tag: https://github.com/SagerNet/sing-box/tree/v1.13.14
- License: GNU General Public License, version 3 or later, with the additional naming restriction stated in the upstream LICENSE file.

Official release binaries are downloaded unchanged by GitHub Actions from:

```text
https://github.com/SagerNet/sing-box/releases/tag/v1.13.14
```

Each tunnelgram release archive includes:

```text
THIRD_PARTY_LICENSES/sing-box-GPL-3.0.txt
THIRD_PARTY_LICENSES/sing-box-source.txt
```

The first file is the full upstream license text. The second file points to the corresponding source code for the bundled version.

`tunnelgram` and sing-box communicate through a generated JSON configuration file and process invocation. No sing-box source code is copied into the Python package.
