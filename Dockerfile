FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# Supabase client config is inlined into the bundle at build time.
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY
RUN npm run build

FROM python:3.12-slim AS production
WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
COPY backend/ ./backend/
RUN uv sync --frozen --no-dev --no-editable

COPY alembic.ini ./
COPY backend/migrations ./backend/migrations
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN mkdir -p /app/data

# DATABASE_URL is provided at runtime (Supabase Postgres). The app creates its
# schema on startup via SQLAlchemy create_all, so no migration step is required.
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
