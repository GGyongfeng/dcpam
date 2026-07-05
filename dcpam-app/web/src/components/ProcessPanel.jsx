import React from "react";

import { ConfigModule } from "./ConfigModule/index.js";
import { SampleImage } from "./SampleImage.jsx";

export function ProcessPanel({ title, images, steps, resolution }) {
  return (
    <section className="section process-panel">
      <ConfigModule defaultOpen={false} />
      <div className="section-title-row">
        <h2>计算过程</h2>
        {title && <span className="process-title">{title}</span>}
      </div>
      {images && (
        <div className="sample-images">
          <SampleImage
            title="前相机"
            src={images.frontSrc}
            spot={images.frontSpot}
            resolution={resolution?.front}
          />
          <SampleImage
            title="后相机"
            src={images.rearSrc}
            spot={images.rearSpot}
            resolution={resolution?.rear}
          />
        </div>
      )}
      <div className="process-list">
        {steps.map((step) => (
          <div className="process-step" key={step.title}>
            <strong>{step.title}</strong>
            <div className="process-lines">
              {step.lines.map((line) => <span key={line}>{line}</span>)}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
