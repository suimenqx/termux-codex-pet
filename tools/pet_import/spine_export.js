'use strict';
// Glue only: the licensed official runtime is fetched separately for personal
// offline export. Neither the runtime nor model artwork is vendored here.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const options = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const {loadImage, createCanvas} = require(options.canvasModule);
const environment = {console, Float32Array, Int16Array, Uint8Array, Uint16Array, Array, Math, Date};
vm.createContext(environment);
vm.runInContext(fs.readFileSync(options.runtime, 'utf8'), environment);
const spine = environment.spine;

async function main() {
  const image = await loadImage(options.texture);
  const atlas = new spine.TextureAtlas(fs.readFileSync(options.atlas, 'utf8'),
    () => new spine.canvas.CanvasTexture(image));
  if (atlas.pages.length !== 1) throw Error('Only a single texture atlas page is supported');
  const binary = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas));
  const data = binary.readSkeletonData(new Uint8Array(fs.readFileSync(options.skeleton)));
  if (!data.version.startsWith('3.8.')) throw Error('Only Spine 3.8 is supported');
  function checkColor(color) {
    if (color && (color.r !== 1 || color.g !== 1 || color.b !== 1)) {
      throw Error('Canvas export does not support tinted attachments/slots');
    }
  }
  for (const skin of data.skins) {
    for (const {attachment} of skin.getAttachments()) {
      if (!(attachment instanceof spine.RegionAttachment) && !(attachment instanceof spine.MeshAttachment)) {
        throw Error('Unsupported attachment: ' + attachment.constructor.name);
      }
      checkColor(attachment.color);
    }
  }
  for (const slot of data.slots) {
    if (slot.blendMode !== spine.BlendMode.Normal || slot.darkColor) {
      throw Error('Unsupported blend mode or two-color tint');
    }
  }
  const {fps, size, supersample: ss, output} = options;
  const clips = options.clips.map(name => {
    const animation = data.findAnimation(name);
    if (!animation || animation.duration <= 0) throw Error('Missing finite clip: ' + name);
    return {name, seconds: animation.duration, totalMs: Math.round(animation.duration * 1000),
      count: Math.ceil(animation.duration * fps)};
  });
  function pose(name) {
    const skeleton = new spine.Skeleton(data);
    const state = new spine.AnimationState(new spine.AnimationStateData(data));
    state.setAnimation(0, name, false);
    return {skeleton, state};
  }
  function apply(p, time) {
    p.skeleton.setToSetupPose();
    p.state.tracks[0].trackTime = time;
    p.state.apply(p.skeleton);
    p.skeleton.updateWorldTransform();
    for (const slot of p.skeleton.slots) checkColor(slot.color);
  }
  let xmin = Infinity, ymin = Infinity, xmax = -Infinity, ymax = -Infinity;
  const offset = new spine.Vector2(), extent = new spine.Vector2();
  for (const clip of clips) {
    const p = pose(clip.name);
    for (let i = 0; i <= clip.count * 2; i++) {
      apply(p, clip.seconds * i / (clip.count * 2));
      p.skeleton.getBounds(offset, extent, []);
      xmin = Math.min(xmin, offset.x); ymin = Math.min(ymin, offset.y);
      xmax = Math.max(xmax, offset.x + extent.x); ymax = Math.max(ymax, offset.y + extent.y);
    }
  }
  // One union viewport for all motions, sampled at twice export density.
  const unit = Math.max(xmax - xmin, ymax - ymin) * 1.08;
  const scale = size * ss / unit, cx = (xmin + xmax) / 2, cy = (ymin + ymax) / 2;
  const large = createCanvas(size * ss, size * ss), ctx = large.getContext('2d');
  const small = createCanvas(size, size), smallCtx = small.getContext('2d');
  smallCtx.imageSmoothingEnabled = true;
  smallCtx.imageSmoothingQuality = 'high';
  const renderer = new spine.canvas.SkeletonRenderer(ctx);
  renderer.triangleRendering = true; // Default image mode silently loses mesh attachments.
  const result = {version: data.version, size, fps, bounds: [xmin, ymin, xmax, ymax], clips: []};
  for (const clip of clips) {
    const p = pose(clip.name), destination = path.join(output, clip.name);
    fs.mkdirSync(destination, {recursive: true});
    const frames = [];
    for (let i = 0; i < clip.count; i++) {
      apply(p, clip.seconds * i / clip.count);
      ctx.resetTransform(); ctx.clearRect(0, 0, large.width, large.height);
      ctx.translate(large.width / 2 - scale * cx, large.height / 2 + scale * cy);
      ctx.scale(scale, -scale); renderer.draw(p.skeleton);
      smallCtx.clearRect(0, 0, size, size); smallCtx.drawImage(large, 0, 0, size, size);
      const file = path.join(destination, String(i).padStart(3, '0') + '.png');
      fs.writeFileSync(file, small.toBuffer('image/png'));
      frames.push({file, duration_ms: Math.round((i + 1) * clip.totalMs / clip.count)
        - Math.round(i * clip.totalMs / clip.count)});
    }
    result.clips.push({...clip, frames});
    console.log(`${clip.name}: ${clip.count} frames, ${clip.totalMs} ms`);
  }
  fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(result, null, 2));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
