"use client";
import { Sparkles } from "lucide-react";
import { Field, Input, Section, Button } from "./Controls";
export default function Inspector({ s, reviewed }) {
  const form = s.brandForm;
  const update = (key) => (value) => s.updateBrandForm(key, value);
  return (
    <aside className="inspector panel" aria-label="Brand settings">
      <div className="panelHeading">
        <div>
          <h2>Brand settings</h2>
          <p>Saved on this device.</p>
        </div>
      </div>
      <div className="inspectorScroll">
        <div className="settingsBody">
          <Field label="Brand preset" hint="Apply a page’s avatar, handle and watermark together.">
            {(id) => (
              <select id={id} value={form.brandPreset} onChange={(e) => s.applyBrandPreset(e.target.value)}>
                <option value="">Custom identity</option>
                {s.brandPresets.map((preset) => (
                  <option key={preset.id} value={preset.id}>{preset.page_name}</option>
                ))}
              </select>
            )}
          </Field>
        </div>
        <Section title="Layout & framing" open={false}>
          <Field label="Branding style">
            {(id) => (
              <select id={id} value={form.style} onChange={(e) => update("style")(e.target.value)}>
                <option value="watermark">Profile below footage</option>
                <option value="header">Header above footage</option>
              </select>
            )}
          </Field>
          <div className="twoFields">
            <Input
              label="Background"
              type="color"
              value={form.bgColor}
              onChange={update("bgColor")}
            />
            <Input
              label="Text"
              type="color"
              value={form.textColor}
              onChange={update("textColor")}
            />
          </div>
          <div className="twoFields">
            {[
              ["maskTop", "Top mask"],
              ["maskBot", "Bottom mask"],
            ].map(([key, label]) => (
              <Field key={key} label={`${label} · ${form[key]}%`}>
                {(id) => (
                  <input
                    id={id}
                    type="range"
                    min="0"
                    max="45"
                    value={form[key]}
                    onChange={(e) => s.updateBrandForm(key, e.target.value)}
                  />
                )}
              </Field>
            ))}
          </div>
          <Field label={`Zoom · ${Number(form.zoom).toFixed(2)}×`}>
            {(id) => (
              <input
                id={id}
                type="range"
                min="1"
                max="2"
                step="0.01"
                value={form.zoom}
                onChange={(e) => update("zoom")(e.target.value)}
              />
            )}
          </Field>
        </Section>
        <Section title="Page identity" open={false}>
          <Input
            label="Page name"
            value={form.pageName}
            onChange={update("pageName")}
          />
          <Input
            label="Handle"
            value={form.handle}
            spellCheck={false}
            onChange={update("handle")}
          />
          <Input
            label="Logo image path"
            value={form.logoPath}
            onChange={update("logoPath")}
            placeholder="C:\\Images\\logo.png…"
          />
          <Input
            label="Logo background"
            type="color"
            value={form.logoColor}
            onChange={update("logoColor")}
          />
        </Section>
        <Section title="Caption">
          <Field label={`Caption · ${form.caption.length}/280`}>
            {(id) => (
              <textarea
                id={id}
                rows="3"
                value={form.caption}
                onChange={(e) => s.updateBrandForm("caption", e.target.value)}
                placeholder="Add a caption…"
              />
            )}
          </Field>
          {form.caption.length > 280 && (
            <p className="warning">
              Caption exceeds the recommended 280 characters. Check wrapping in
              the preview.
            </p>
          )}
          <Input
            label="Font size (px)"
            type="number"
            min="1"
            value={form.captionFontSize}
            onChange={update("captionFontSize")}
          />
        </Section>
        {form.brandPreset && (
          <Section title="Watermark" open={false}>
            <Field label="Position">
              {(id) => (
                <select
                  id={id}
                  value={form.watermarkPosition}
                  onChange={(e) => update("watermarkPosition")(e.target.value)}
                >
                  <option value="top-left">Top left</option>
                  <option value="top-right">Top right</option>
                  <option value="bottom-left">Bottom left</option>
                  <option value="bottom-right">Bottom right</option>
                  <option value="off">Off</option>
                </select>
              )}
            </Field>
            <Input
              label={`Opacity · ${form.watermarkOpacity}%`}
              type="range"
              min="0"
              max="100"
              value={form.watermarkOpacity}
              onChange={update("watermarkOpacity")}
            />
            <Input
              label={`Width · ${form.watermarkWidth}%`}
              type="range"
              min="1"
              max="100"
              value={form.watermarkWidth}
              onChange={update("watermarkWidth")}
            />
          </Section>
        )}
        <Section title="Files & background" open={false}>
          <Input
            label="Background image path"
            value={form.bgPath}
            onChange={update("bgPath")}
            hint="Overrides the background color."
          />
          <Input
            label="Output folder"
            value={form.outputFolder}
            onChange={update("outputFolder")}
            placeholder="branded_videos/…"
            hint="Leave empty for the default folder. Use an absolute path for a custom folder."
          />
        </Section>
      </div>
      <div className="renderBar">
        <div>
          <strong>{s.selectedVideos.length} clips in this batch</strong>
          <span>
            {!s.selectedVideos.length
              ? "Select clips to begin"
              : !s.previewFresh
                ? "Generate a preview to check the frame"
                : !reviewed
                  ? "Review the preview to continue"
                  : "Ready to render with these settings"}
          </span>
        </div>
        <Button
          primary
          busy={s.brandTask.state === "processing"}
          disabled={
            !!s.clipImport?.name ||
            !s.selectedVideos.length ||
            !s.previewFresh ||
            !reviewed ||
            s.isPreviewLoading ||
            s.brandTask.state === "processing"
          }
          onClick={s.startBranding}
        >
          <Sparkles size={16} />
          {s.brandTask.state === "processing"
            ? "Rendering…"
            : `Render ${s.selectedVideos.length || ""} ${s.selectedVideos.length === 1 ? "clip" : "clips"}`}
        </Button>
      </div>
    </aside>
  );
}
