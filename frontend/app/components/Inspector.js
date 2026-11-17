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
        <Section title="Layout & framing">
          <Field label="Branding style">
            {(id) => (
              <select id={id} value="header" disabled>
                <option value="header">Header</option>
                <option value="watermark">Corner watermark</option>
              </select>
            )}
          </Field>
          <p className="hint">
            Header branding is available. Watermark styling and zoom are not
            connected in this version.
          </p>
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
                    max="50"
                    value={form[key]}
                    onChange={(e) => s.updateBrandForm(key, e.target.value)}
                  />
                )}
              </Field>
            ))}
          </div>
          <Field label="Zoom">
            {(id) => (
              <input
                id={id}
                type="range"
                min="1"
                max="2"
                step="0.01"
                value="1"
                disabled
              />
            )}
          </Field>
        </Section>
        <Section title="Page identity">
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
        <Section title="Watermark" open={false}>
          <p className="hint">
            Watermark settings are not connected in this version.
          </p>
          <fieldset disabled>
            <Field label="Position">
              {(id) => (
                <select id={id}>
                  <option>Bottom right</option>
                </select>
              )}
            </Field>
            <Input
              label="Opacity"
              type="range"
              value="55"
              onChange={() => {}}
            />
            <Input label="Scale" type="range" value="50" onChange={() => {}} />
          </fieldset>
        </Section>
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
                ? "Wait for a current preview"
                : !reviewed
                  ? "Review the preview to continue"
                  : "Ready to render with these settings"}
          </span>
        </div>
        <Button
          primary
          busy={s.brandTask.state === "processing"}
          disabled={
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
