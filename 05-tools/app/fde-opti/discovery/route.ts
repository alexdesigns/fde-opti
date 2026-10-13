// GET /fde-opti/discovery: the URL registered in the Optimizely AI tool registry ("OptiThera Regulated Content Readiness").
// Static metadata only. Lists validate_approved_claim and submit_readiness_result.
import { REGISTRY_DISCOVERY } from "../../../shared/registry";

export function GET() {
  return Response.json(REGISTRY_DISCOVERY);
}
