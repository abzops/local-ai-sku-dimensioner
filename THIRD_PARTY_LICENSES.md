# Third-Party Licences

This file records direct runtime dependencies selected for the application. Transitive and
development dependencies are enumerated by the generated lock files and must be reviewed before a
release is distributed.

| Dependency | Purpose | Licence | Source |
|---|---|---|---|
| FastAPI | HTTP API framework | MIT | <https://github.com/fastapi/fastapi> |
| Uvicorn | Local ASGI server | BSD-3-Clause | <https://github.com/encode/uvicorn> |
| Pydantic / pydantic-settings | Validation and typed configuration | MIT | <https://github.com/pydantic/pydantic> |
| SQLAlchemy | Database toolkit | MIT | <https://github.com/sqlalchemy/sqlalchemy> |
| Alembic | Database migrations | MIT | <https://github.com/sqlalchemy/alembic> |
| Pillow | Local image decoding and format validation | HPND | <https://github.com/python-pillow/Pillow> |
| NumPy | Deterministic marker, foreground, contour, reconciliation, and geometry arrays | BSD-3-Clause | <https://github.com/numpy/numpy> |
| OpenCV contrib, headless Python package | Local ArUco, rectification, foreground, contour geometry, and previews | Apache-2.0 | <https://github.com/opencv/opencv-python> |
| python-multipart | Multipart form parsing | Apache-2.0 | <https://github.com/Kludex/python-multipart> |
| React / React DOM | Web interface | MIT | <https://github.com/facebook/react> |
| React Router | Client-side routing | MIT | <https://github.com/remix-run/react-router> |
| TanStack Query | Server-state management | MIT | <https://github.com/TanStack/query> |
| Vite | Frontend development and build tooling | MIT | <https://github.com/vitejs/vite> |

## Local AI models

No AI model or model weights are selected, downloaded, embedded, or distributed in Phase 3. A model
licence and commercial-use review is required before Phase 4 introduces any model.
