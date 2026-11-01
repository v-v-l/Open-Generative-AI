// Preserve upstream registry and helpers; local models use explicit dimensions.
export * from "../../packages/studio/src/models.js";
import * as upstream from "../../packages/studio/src/models.js";
const ratios = (model) => model?.inputs?.aspect_ratio?.enum || [];
export const getAspectRatiosForModel = (id) =>
  ratios(upstream.getModelById(id));
export const getAspectRatiosForI2IModel = (id) =>
  ratios(upstream.getI2IModelById(id));
export const getAspectRatiosForVideoModel = (id) =>
  ratios(upstream.getVideoModelById(id));
export const getAspectRatiosForI2VModel = (id) =>
  ratios(upstream.getI2VModelById(id));
