import React from "react";

export function IconButton({ className = "", icon, text = "", label, onClick }) {
  return (
    <button type="button" className={`icon-button ${className}`} title={label} aria-label={label} onClick={onClick}>
      <span className={text && icon ? "button-icon" : ""}>{icon}</span>
      {text}
    </button>
  );
}
