import AppKit
import Foundation
let args = CommandLine.arguments
let raw = try String(contentsOfFile: args[1], encoding: .utf8)
let lines = raw.components(separatedBy: "\n")
let width = max(1680, (lines.map { $0.utf16.count }.max() ?? 160) * 10 + 48)
let height = 1160
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
NSColor(calibratedWhite: 0.065, alpha: 1).setFill()
NSRect(x: 0, y: 0, width: width, height: height).fill()
let titleAttrs: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 20, weight: .semibold), .foregroundColor: NSColor.white]
(args[3] as NSString).draw(at: NSPoint(x: 24,y: height-44), withAttributes: titleAttrs)
let subtitle: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 13), .foregroundColor: NSColor.lightGray]
("Live tmux capture rendered for review • account/usage rows omitted where present • target e1a6b78" as NSString).draw(at: NSPoint(x:24,y:height-68),withAttributes:subtitle)
let attrs: [NSAttributedString.Key: Any] = [.font: NSFont.monospacedSystemFont(ofSize: 15, weight: .regular), .foregroundColor: NSColor(calibratedWhite: 0.91, alpha: 1)]
for (i,line) in lines.enumerated() {
    (line as NSString).draw(at: NSPoint(x: 24, y: height-104-i*20), withAttributes: attrs)
}
NSGraphicsContext.restoreGraphicsState()
try rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath:args[2]))
