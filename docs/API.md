# API

Interactive docs are served by the backend at `/docs` (Swagger UI).

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness |
| GET | `/api/meta/status` | Data mode, Google and AI configuration |
| GET | `/api/meta/options` | Preset interests, diets, categories, modes |
| POST | `/api/trips` | Generate and save an itinerary |
| POST | `/api/trips/preview` | Generate without saving |
| GET | `/api/trips` / `/api/trips/{id}` | List / get saved trips |
| POST | `/api/trips/{id}/regenerate` | Re-run with the saved request |
| DELETE | `/api/trips/{id}` | Delete a trip |
| POST | `/api/trips/{id}/live` | Live position, then next stop, fresh estimates and alerts |
| POST | `/api/routes/compare` | Compare modes between two points |
| GET | `/api/geo/cities?q=` | City autocomplete (2+ letters) |
| GET | `/api/geo/addresses?q=&lat=&lng=` | Address/hotel suggestions near a city |
| POST | `/api/nlp/parse-trip` | Free-text trip description → form fields |
