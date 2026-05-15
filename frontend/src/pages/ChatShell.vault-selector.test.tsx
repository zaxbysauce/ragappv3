import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { resolve } from "path";

describe("ChatShell VaultSelector Integration", () => {
  const chatShellPath = resolve(__dirname, "./ChatShell.tsx");
  const chatShellContent = readFileSync(chatShellPath, "utf-8");

  describe("VaultSelector import", () => {
    it("imports VaultSelector from @/components/vault/VaultSelector", () => {
      const hasImport = chatShellContent.includes(
        'import { VaultSelector } from "@/components/vault/VaultSelector"'
      );
      expect(hasImport).toBe(true);
    });
  });

  describe("VaultSelector rendering in header", () => {
    it("renders VaultSelector in the header JSX", () => {
      // VaultSelector should appear between session title span and export button
      const headerSectionMatch = chatShellContent.match(
        /<header[^>]*>[\s\S]*?<\/header>/
      );
      expect(headerSectionMatch).not.toBeNull();

      const headerContent = headerSectionMatch![0];

      // Check VaultSelector is present
      expect(headerContent).toContain("<VaultSelector");

      // Check VaultSelector appears after activeSessionTitle
      const titleIndex = headerContent.indexOf("activeSessionTitle");
      const vaultIndex = headerContent.indexOf("<VaultSelector");
      expect(vaultIndex).toBeGreaterThan(titleIndex);

      // Check VaultSelector appears before export button (Download)
      const downloadIndex = headerContent.indexOf("<Download");
      expect(vaultIndex).toBeLessThan(downloadIndex);
    });

    it("VaultSelector is rendered as self-closing component", () => {
      // VaultSelector should be rendered as <VaultSelector /> (self-closing)
      const vaultSelectorMatch = chatShellContent.match(/<VaultSelector\s*(\/?>|\s+className=)/);
      expect(vaultSelectorMatch).not.toBeNull();
    });

    it("VaultSelector is positioned after session title conditional and before export button", () => {
      // Extract the relevant portion between activeSessionTitle block and Download button
      const afterTitle = chatShellContent.substring(
        chatShellContent.indexOf("{activeSessionTitle &&"),
        chatShellContent.indexOf("<Download")
      );

      // VaultSelector should appear in this section
      expect(afterTitle).toContain("<VaultSelector />");
    });

    it("VaultSelector appears after the fallback flex-1 div and before export button", () => {
      // The structure should be: {!activeSessionTitle && <div className="flex-1" />} <VaultSelector /> <Button export>
      const flexOneIndex = chatShellContent.indexOf('className="flex-1"');
      const vaultIndex = chatShellContent.indexOf("<VaultSelector");
      const downloadIndex = chatShellContent.indexOf("<Download");

      expect(flexOneIndex).toBeGreaterThan(0);
      expect(vaultIndex).toBeGreaterThan(flexOneIndex);
      expect(vaultIndex).toBeLessThan(downloadIndex);
    });
  });

  describe("Header structure", () => {
    it("header contains PanelLeft, session title, VaultSelector, export, and PanelRight in that relative order", () => {
      const headerMatch = chatShellContent.match(
        /<header[^>]*>[\s\S]*?<\/header>/
      );
      expect(headerMatch).not.toBeNull();

      const header = headerMatch![0];

      const panelLeftIdx = header.indexOf("PanelLeft");
      const titleIdx = header.indexOf("activeSessionTitle");
      const vaultIdx = header.indexOf("<VaultSelector");
      const downloadIdx = header.indexOf("<Download");
      const panelRightIdx = header.indexOf("PanelRight");

      // All should be present
      expect(panelLeftIdx).toBeGreaterThan(0);
      expect(titleIdx).toBeGreaterThan(0);
      expect(vaultIdx).toBeGreaterThan(0);
      expect(downloadIdx).toBeGreaterThan(0);
      expect(panelRightIdx).toBeGreaterThan(0);

      // Order: PanelLeft < Title < VaultSelector < Download < PanelRight
      expect(panelLeftIdx).toBeLessThan(titleIdx);
      expect(titleIdx).toBeLessThan(vaultIdx);
      expect(vaultIdx).toBeLessThan(downloadIdx);
      expect(downloadIdx).toBeLessThan(panelRightIdx);
    });
  });
});
