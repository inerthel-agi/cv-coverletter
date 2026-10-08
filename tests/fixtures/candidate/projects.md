<!-- FICTITIOUS TEST FIXTURE -->
# Projects — Camille Testard

## RouteWise {#routewise}
- Dates: Jan 2026 – Apr 2026. Capstone, team of 3. Status: used in a pilot.
- Problem: volunteer coordinators of the Northbridge Community Pantry planned delivery routes for volunteer drivers by hand.
- My part: I owned the backend API (Python, FastAPI) and the route-batching heuristic that groups stops into routes. I designed the PostgreSQL schema for stops, drivers and routes and exposed it through REST endpoints. I wrote pytest tests for the API endpoints. Teammates built the Leaflet (JavaScript) map front end.
- Docker: used for local development only; the app was never deployed with Kubernetes.
- Result: used by 4 volunteer coordinators during a 3-week pilot. In a survey of the 4 coordinators, they reported that planning time per shift fell from about 25 minutes to about 10 minutes. No other measurement.

## ShelfScan {#shelfscan}
- Dates: Oct 2025 – Dec 2025. Computer Vision course project. Status: prototype.
- What: a tool that counts products on shelf photos. I built image preprocessing with OpenCV and trained a detection model with PyTorch.
- Data: trained and tested on a public shelf-image dataset.
- Result: not used in production; accuracy not formally measured. No metrics.

## AltCheck {#altcheck}
- Dates: Jun 2025 – Aug 2025. Personal project. Status: used.
- What: a GitHub Action (JavaScript, Node.js) that flags images without alt text in HTML pull requests.
- Result: adopted by 3 student club websites. No other metric.
