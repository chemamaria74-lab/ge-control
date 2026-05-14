const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const outDir = path.resolve(__dirname, "..", "static", "img");
const COLORS = {
  wine: [122, 30, 44, 255],
  wineDark: [91, 15, 29, 255],
  gold: [200, 169, 107, 255],
  black: [17, 17, 17, 255],
  white: [245, 245, 245, 255],
  transparent: [0, 0, 0, 0],
};

function crc32(buf) {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return ~c >>> 0;
}

function chunk(type, data) {
  const t = Buffer.from(type);
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([t, data])), 0);
  return Buffer.concat([len, t, data, crc]);
}

function encodePng(width, height, data) {
  const rows = [];
  for (let y = 0; y < height; y++) {
    rows.push(Buffer.concat([Buffer.from([0]), data.subarray(y * width * 4, (y + 1) * width * 4)]));
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(Buffer.concat(rows))),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

function makeCanvas(width, height, bg = COLORS.transparent) {
  const data = Buffer.alloc(width * height * 4);
  for (let i = 0; i < width * height; i++) {
    data[i * 4] = bg[0];
    data[i * 4 + 1] = bg[1];
    data[i * 4 + 2] = bg[2];
    data[i * 4 + 3] = bg[3];
  }
  return { width, height, data };
}

function setPx(c, x, y, color) {
  x = Math.round(x);
  y = Math.round(y);
  if (x < 0 || x >= c.width || y < 0 || y >= c.height) return;
  const i = (y * c.width + x) * 4;
  c.data[i] = color[0];
  c.data[i + 1] = color[1];
  c.data[i + 2] = color[2];
  c.data[i + 3] = color[3];
}

function fillRect(c, x, y, w, h, color) {
  for (let yy = Math.max(0, Math.floor(y)); yy < Math.min(c.height, Math.ceil(y + h)); yy++) {
    for (let xx = Math.max(0, Math.floor(x)); xx < Math.min(c.width, Math.ceil(x + w)); xx++) setPx(c, xx, yy, color);
  }
}

function pointInPoly(x, y, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const xi = pts[i][0], yi = pts[i][1];
    const xj = pts[j][0], yj = pts[j][1];
    const intersect = ((yi > y) !== (yj > y)) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

function fillPoly(c, pts, color) {
  const minX = Math.floor(Math.min(...pts.map(p => p[0])));
  const maxX = Math.ceil(Math.max(...pts.map(p => p[0])));
  const minY = Math.floor(Math.min(...pts.map(p => p[1])));
  const maxY = Math.ceil(Math.max(...pts.map(p => p[1])));
  for (let y = minY; y <= maxY; y++) {
    for (let x = minX; x <= maxX; x++) {
      if (pointInPoly(x + 0.5, y + 0.5, pts)) setPx(c, x, y, color);
    }
  }
}

function fillEllipse(c, cx, cy, rx, ry, color) {
  for (let y = Math.floor(cy - ry); y <= Math.ceil(cy + ry); y++) {
    for (let x = Math.floor(cx - rx); x <= Math.ceil(cx + rx); x++) {
      const v = ((x - cx) ** 2) / (rx ** 2) + ((y - cy) ** 2) / (ry ** 2);
      if (v <= 1) setPx(c, x, y, color);
    }
  }
}

function drawLine(c, x1, y1, x2, y2, color, thickness = 5) {
  const steps = Math.max(Math.abs(x2 - x1), Math.abs(y2 - y1)) * 2;
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const x = x1 + (x2 - x1) * t;
    const y = y1 + (y2 - y1) * t;
    for (let yy = -thickness; yy <= thickness; yy++) {
      for (let xx = -thickness; xx <= thickness; xx++) {
        if (xx * xx + yy * yy <= thickness * thickness) setPx(c, x + xx, y + yy, color);
      }
    }
  }
}

function drawGE(c, x, y, scale, light = false) {
  const red = light ? COLORS.white : COLORS.wine;
  const gold = COLORS.gold;
  const sx = v => x + v * scale;
  const sy = v => y + v * scale;

  fillEllipse(c, sx(300), sy(338), 270 * scale, 250 * scale, red);
  fillEllipse(c, sx(338), sy(338), 160 * scale, 150 * scale, COLORS.transparent);
  fillRect(c, sx(300), sy(90), 310 * scale, 96 * scale, COLORS.transparent);
  fillRect(c, sx(318), sy(384), 250 * scale, 106 * scale, COLORS.transparent);
  fillRect(c, sx(372), sy(286), 300 * scale, 96 * scale, red);
  fillPoly(c, [[sx(660), sy(90)], [sx(946), sy(90)], [sx(918), sy(185)], [sx(688), sy(185)]], gold);
  fillRect(c, sx(692), sy(286), 222 * scale, 96 * scale, red);
  fillPoly(c, [[sx(692), sy(490)], [sx(938), sy(490)], [sx(914), sy(590)], [sx(692), sy(590)]], red);
}

function drawLetter(c, ch, x, y, w, h, color) {
  const l = (ax, ay, bx, by) => drawLine(c, x + ax * w, y + ay * h, x + bx * w, y + by * h, color, Math.max(3, w * 0.045));
  if (ch === "C") { l(.88, .04, .20, .04); l(.20, .04, .06, .50); l(.06, .50, .20, .96); l(.20, .96, .88, .96); }
  if (ch === "O") { l(.20, .04, .80, .04); l(.80, .04, .94, .50); l(.94, .50, .80, .96); l(.80, .96, .20, .96); l(.20, .96, .06, .50); l(.06, .50, .20, .04); }
  if (ch === "N") { l(.06, .96, .06, .04); l(.06, .04, .94, .96); l(.94, .96, .94, .04); }
  if (ch === "T") { l(.06, .04, .94, .04); l(.50, .04, .50, .96); }
  if (ch === "R") { l(.06, .96, .06, .04); l(.06, .04, .72, .04); l(.72, .04, .91, .33); l(.91, .33, .72, .58); l(.72, .58, .06, .58); l(.42, .58, .94, .96); }
  if (ch === "L") { l(.06, .04, .06, .96); l(.06, .96, .94, .96); }
}

function drawWord(c, word, x, y, size, color, gap = 34) {
  let pos = x;
  for (const ch of word) {
    drawLetter(c, ch, pos, y, size * 0.58, size, color);
    pos += size * 0.58 + gap;
  }
}

function pngIsotype(size, light = false, iconBg = null) {
  const c = makeCanvas(size, size, iconBg || COLORS.transparent);
  const s = size / 1024;
  drawGE(c, 42 * s, 208 * s, 0.86 * s, light);
  return encodePng(size, size, c.data);
}

function pngLogo(light = false) {
  const c = makeCanvas(1800, 500, COLORS.transparent);
  drawGE(c, 44, 78, 0.54, light);
  drawLine(c, 600, 70, 600, 330, COLORS.gold, 2);
  drawWord(c, "CONTROL", 700, 125, 92, light ? COLORS.white : COLORS.black, 45);
  return encodePng(c.width, c.height, c.data);
}

function write(name, buf) {
  fs.writeFileSync(path.join(outDir, name), buf);
  console.log("generated", name);
}

write("ge-isotype.png", pngIsotype(1024, false));
write("ge-isotype-light.png", pngIsotype(1024, true));
write("ge-control-logo.png", pngLogo(false));
write("ge-control-logo-light.png", pngLogo(true));
write("apple-touch-icon.png", pngIsotype(180, true, COLORS.wineDark));
write("ge-icon-192.png", pngIsotype(192, true, COLORS.wineDark));
write("ge-icon-512.png", pngIsotype(512, true, COLORS.wineDark));
