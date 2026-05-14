const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const root = path.resolve(__dirname, "..", "static", "img");

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

function png(width, height, draw) {
  const rows = [];
  for (let y = 0; y < height; y++) {
    const row = Buffer.alloc(1 + width * 4);
    row[0] = 0;
    for (let x = 0; x < width; x++) {
      const [r, g, b, a] = draw(x / width, y / height, x, y);
      const i = 1 + x * 4;
      row[i] = r; row[i + 1] = g; row[i + 2] = b; row[i + 3] = a;
    }
    rows.push(row);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; ihdr[9] = 6;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(Buffer.concat(rows))),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

function rect(x, y, x1, y1, x2, y2) {
  return x >= x1 && x <= x2 && y >= y1 && y <= y2;
}

function circle(x, y, cx, cy, r) {
  return Math.hypot(x - cx, y - cy) <= r;
}

function geIcon(width, height, dark = true) {
  const bg = dark ? [91, 15, 29, 255] : [245, 245, 245, 255];
  const fg = dark ? [245, 245, 245, 255] : [122, 30, 44, 255];
  const gold = [200, 169, 107, 255];
  return png(width, height, (x, y) => {
    const rounded = circle(x, y, .5, .5, .68);
    if (!rounded) return [0, 0, 0, 0];
    let color = bg;
    const gOuter = circle(x, y, .44, .53, .33);
    const gInner = circle(x, y, .49, .53, .20);
    const openRight = x > .47 && y > .39 && y < .66;
    const gShape = gOuter && (!gInner || openRight);
    const gBar = rect(x, y, .42, .49, .72, .59);
    const eTop = rect(x, y, .61, .31, .82, .42);
    const eMid = rect(x, y, .61, .49, .78, .59);
    if (gShape || gBar || eMid) color = fg;
    if (eTop) color = gold;
    return color;
  });
}

const GLYPHS = {
  C: ["11110", "10000", "10000", "10000", "10000", "10000", "11110"],
  O: ["11110", "10010", "10010", "10010", "10010", "10010", "11110"],
  N: ["10010", "11010", "10110", "10010", "10010", "10010", "10010"],
  T: ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
  R: ["11110", "10010", "10010", "11110", "10100", "10010", "10010"],
  L: ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
};

function drawGlyph(buf, width, height, ch, ox, oy, scale, color) {
  const rows = GLYPHS[ch];
  if (!rows) return;
  for (let gy = 0; gy < rows.length; gy++) {
    for (let gx = 0; gx < rows[gy].length; gx++) {
      if (rows[gy][gx] !== "1") continue;
      for (let py = 0; py < scale; py++) {
        for (let px = 0; px < scale; px++) {
          const x = ox + gx * scale + px;
          const y = oy + gy * scale + py;
          if (x < 0 || x >= width || y < 0 || y >= height) continue;
          const idx = (y * width + x) * 4;
          buf[idx] = color[0]; buf[idx + 1] = color[1]; buf[idx + 2] = color[2]; buf[idx + 3] = color[3];
        }
      }
    }
  }
}

function putPixel(buf, width, height, x, y, color) {
  if (x < 0 || x >= width || y < 0 || y >= height) return;
  const idx = (Math.round(y) * width + Math.round(x)) * 4;
  buf[idx] = color[0]; buf[idx + 1] = color[1]; buf[idx + 2] = color[2]; buf[idx + 3] = color[3];
}

function drawLine(buf, width, height, x1, y1, x2, y2, color, thickness = 5) {
  const steps = Math.max(Math.abs(x2 - x1), Math.abs(y2 - y1)) * 2;
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const x = x1 + (x2 - x1) * t;
    const y = y1 + (y2 - y1) * t;
    for (let yy = -thickness; yy <= thickness; yy++) {
      for (let xx = -thickness; xx <= thickness; xx++) {
        if (xx * xx + yy * yy <= thickness * thickness) putPixel(buf, width, height, Math.round(x + xx), Math.round(y + yy), color);
      }
    }
  }
}

function drawLetter(buf, width, height, ch, x, y, w, h, color) {
  const l = (ax, ay, bx, by) => drawLine(buf, width, height, x + ax * w, y + ay * h, x + bx * w, y + by * h, color, 4);
  if (ch === "C") { l(.92, .05, .18, .05); l(.18, .05, .05, .50); l(.05, .50, .18, .95); l(.18, .95, .92, .95); }
  if (ch === "O") { l(.18, .05, .82, .05); l(.82, .05, .95, .50); l(.95, .50, .82, .95); l(.82, .95, .18, .95); l(.18, .95, .05, .50); l(.05, .50, .18, .05); }
  if (ch === "N") { l(.05, .95, .05, .05); l(.05, .05, .95, .95); l(.95, .95, .95, .05); }
  if (ch === "T") { l(.05, .05, .95, .05); l(.50, .05, .50, .95); }
  if (ch === "R") { l(.05, .95, .05, .05); l(.05, .05, .76, .05); l(.76, .05, .92, .33); l(.92, .33, .76, .56); l(.76, .56, .05, .56); l(.42, .56, .95, .95); }
  if (ch === "L") { l(.05, .05, .05, .95); l(.05, .95, .95, .95); }
}

function drawWord(buf, width, height, word, x, y, color) {
  const w = 54, h = 78, gap = 28;
  for (const ch of word) {
    drawLetter(buf, width, height, ch, x, y, w, h, color);
    x += w + gap;
  }
}

function fullLogo(width, height, dark = false) {
  const bg = dark ? [91, 15, 29, 255] : [245, 245, 245, 255];
  const fg = dark ? [245, 245, 245, 255] : [122, 30, 44, 255];
  const text = dark ? [245, 245, 245, 255] : [17, 17, 17, 255];
  const gold = [200, 169, 107, 255];
  const data = Buffer.alloc(width * height * 4);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = (y * width + x) * 4;
      data[idx] = bg[0]; data[idx + 1] = bg[1]; data[idx + 2] = bg[2]; data[idx + 3] = bg[3];
    }
  }
  const icon = geIcon(150, 150, dark);
  // Decode is avoided intentionally; redraw a simplified mark directly.
  const mark = (x, y) => {
    const nx = (x - 58) / 150;
    const ny = (y - 34) / 150;
    const gOuter = circle(nx, ny, .44, .53, .33);
    const gInner = circle(nx, ny, .49, .53, .20);
    const openRight = nx > .47 && ny > .39 && ny < .66;
    const gShape = gOuter && (!gInner || openRight);
    const gBar = rect(nx, ny, .42, .49, .72, .59);
    const eTop = rect(nx, ny, .61, .31, .82, .42);
    const eMid = rect(nx, ny, .61, .49, .78, .59);
    if (eTop) return gold;
    if (gShape || gBar || eMid) return fg;
    return null;
  };
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const c = mark(x, y);
      if (!c) continue;
      const idx = (y * width + x) * 4;
      data[idx] = c[0]; data[idx + 1] = c[1]; data[idx + 2] = c[2]; data[idx + 3] = c[3];
    }
  }
  for (let y = 34; y < 184; y++) {
    for (let x = 254; x < 256; x++) {
      const idx = (y * width + x) * 4;
      data[idx] = gold[0]; data[idx + 1] = gold[1]; data[idx + 2] = gold[2]; data[idx + 3] = gold[3];
    }
  }
  drawWord(data, width, height, "CONTROL", 304, 66, text);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; ihdr[9] = 6;
  const rows = [];
  for (let y = 0; y < height; y++) rows.push(Buffer.concat([Buffer.from([0]), data.subarray(y * width * 4, (y + 1) * width * 4)]));
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(Buffer.concat(rows))),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

function write(file, buffer) {
  fs.writeFileSync(path.join(root, file), buffer);
  console.log("generated", file);
}

write("ge-icon-192.png", geIcon(192, 192, true));
write("ge-icon-512.png", geIcon(512, 512, true));
write("ge-isotype.png", geIcon(512, 512, false));
write("ge-isotype-light.png", geIcon(512, 512, true));
write("apple-touch-icon.png", geIcon(180, 180, true));
write("ge-control-logo.png", fullLogo(920, 220, false));
write("ge-control-logo-light.png", fullLogo(920, 220, true));
