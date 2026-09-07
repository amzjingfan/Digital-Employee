# Source manifest

Downloaded from official GitHub codeload endpoints on 2026-08-29.

| Component | Branch | Commit | Local source | Archive SHA-256 |
|---|---|---|---|---|
| StaffDeck | `main` | `b472ac46d8ed9e9cc41d9f663ac3b45497f92d44` | `D:\saas\third_party\StaffDeck` | `EB2B06FD027D8823D01820BA70C7D47ECB096253DF16A1FB48AEFB32B92707D4` |
| Casdoor | `master` | `a551ab77480b744d6dc15e54fc9a349e66e8b365` | `D:\saas\third_party\casdoor` | `7C6C7F6DCD373FA4A1355DA62AC9C5235DF0ADF8B9D12001BCA8889EF30AC754` |
| PyCasbin | `master` | `bf5a94be899c3eb14e9d9509904a3b38d9f2cf71` | `D:\saas\third_party\pycasbin` | `F8A5B8373C712B741E972DBB74F63DAFE7D65718AD8D25B70E4A586D4563BA97` |

The archives are retained in `D:\saas\third_party_archives`. They do not include Git history.

## Container images

The Docker Hub endpoint was unavailable from this workstation. The OCI index and linux/amd64 manifest digests below matched independently through `docker.1ms.run` and `docker.m.daocloud.io` before download.

| Image | OCI index digest | linux/amd64 manifest digest |
|---|---|---|
| `pgvector/pgvector:0.8.6-pg16-bookworm` | `sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b` | `sha256:eac621400b7b7ff52493883e41e930e3d104695fea5b68cc0c42370cf7880067` |
| `casbin/casdoor:3.161.1` | `sha256:f6dfa0cd6fca81b507c219d8eec28ec074256283ddc4018e20521627188e6f99` | `sha256:25c8df27f3680fd352c7074c3189e578c4c61092c4ee7e2194068ef669366474` |
