const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:5000";

const STORAGE_KEY = "reelStudio.brandForm.v1";
const DL_STORAGE_KEY = "reelStudio.downloadForm.v1";
const CAPTION_LIMIT = 280;

const brandDefaults = {
  brandPreset: "",
  style: "watermark",
  zoom: 1,
  watermarkPosition: "top-left",
  watermarkOpacity: 14,
  watermarkWidth: 22,
  pageName: "epicmemeoclock",
  handle: "@epicmemeoclock",
  logoColor: "#ffffff",
  logoPath: "",
  caption: "We post daily follow for more",
  captionFontSize: 52,
  maskTop: 9,
  maskBot: 27,
  bgColor: "#000000",
  textColor: "#ffffff",
  bgPath: "",
  outputFolder: "",
};

function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

function classNames(...values) {
  return values.filter(Boolean).join(" ");
}

function groupFiles(files) {
  return files.reduce((acc, file) => {
    const key = file.folder || "Root";
    if (!acc[key]) acc[key] = [];
    acc[key].push(file);
    return acc;
  }, {});
}

function toRgbArray(hex) {
  return [
    Number.parseInt(hex.slice(1, 3), 16),
    Number.parseInt(hex.slice(3, 5), 16),
    Number.parseInt(hex.slice(5, 7), 16),
  ];
}

// Windows "Copy as path" wraps paths in double quotes, which breaks
// os.path.isfile on the backend. Strip surrounding quotes/whitespace.
function cleanPath(value) {
  return (value || "")
    .trim()
    .replace(/^["']+|["']+$/g, "")
    .trim();
}

function buildProfileConfig(brandForm) {
  const pageName = brandForm.pageName.trim();
  const handle = brandForm.handle.trim();
  const logoPath = cleanPath(brandForm.logoPath);

  if (!pageName && !handle) {
    return null;
  }

  return {
    page_name: pageName,
    handle,
    logo_path: logoPath,
    logo_color: toRgbArray(brandForm.logoColor),
  };
}

function buildConfig(brandForm) {
  return {
    ...(brandForm.brandPreset && { brand_preset: brandForm.brandPreset }),
    style: brandForm.style === "header" ? "header" : "watermark",
    zoom_factor: Number(brandForm.zoom) || 1,
    video_watermark_position: brandForm.watermarkPosition || "top-left",
    video_watermark_opacity: Number(brandForm.watermarkOpacity ?? 14) / 100,
    video_watermark_width_fraction: Number(brandForm.watermarkWidth ?? 22) / 100,
    bg_color: toRgbArray(brandForm.bgColor),
    text_color: toRgbArray(brandForm.textColor),
    bg_path: cleanPath(brandForm.bgPath),
    font_size: Number(brandForm.captionFontSize) || 52,
  };
}

function getProgress(current, total) {
  if (!total) {
    return 0;
  }
  return Math.min(Math.round((current / total) * 100), 100);
}

function outputVideoUrl(path) {
  return apiUrl(`/api/video/${encodeURIComponent(path)}`);
}

async function requestJson(path, options) {
  let response;
  try {
    response = await fetch(apiUrl(path), options);
  } catch {
    // fetch only rejects on network failure — almost always a stopped backend.
    throw new Error(
      `Cannot reach the backend at ${API_BASE_URL}. Is the Flask server running?`,
    );
  }

  let data;
  try {
    data = await response.json();
  } catch {
    // Non-JSON body (Flask HTML error page, proxy error, ...)
    throw new Error(
      `Backend returned a non-JSON response (HTTP ${response.status}).`,
    );
  }

  if (!response.ok || data.error) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

export {
  API_BASE_URL,
  STORAGE_KEY,
  DL_STORAGE_KEY,
  CAPTION_LIMIT,
  brandDefaults,
  apiUrl,
  classNames,
  groupFiles,
  cleanPath,
  buildProfileConfig,
  buildConfig,
  getProgress,
  outputVideoUrl,
  requestJson,
};
