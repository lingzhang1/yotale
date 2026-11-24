import XCTest
import AVFoundation
import UIKit
@testable import Story

/// Synthetic media for pipeline tests. Nothing here is derived from personal footage.
enum SyntheticMedia {

    /// A small H.264 video whose frame colour is keyed to the second. Exercises the REAL MomentFrameExtractor.
    static func makeVideo(seconds: Int, fps: Int32 = 10) async throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("p1f-\(UUID().uuidString).mp4")
        let writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
        let settings: [String: Any] = [AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: 320, AVVideoHeightKey: 240]
        let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(
            assetWriterInput: input,
            sourcePixelBufferAttributes: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
                                          kCVPixelBufferWidthKey as String: 320, kCVPixelBufferHeightKey as String: 240])
        writer.add(input)
        XCTAssertTrue(writer.startWriting())
        writer.startSession(atSourceTime: .zero)
        for i in 0..<(seconds * Int(fps)) {
            while !input.isReadyForMoreMediaData { try await Task.sleep(nanoseconds: 2_000_000) }
            var pb: CVPixelBuffer?
            CVPixelBufferCreate(nil, 320, 240, kCVPixelFormatType_32BGRA, nil, &pb)
            guard let buf = pb else { continue }
            CVPixelBufferLockBaseAddress(buf, [])
            if let base = CVPixelBufferGetBaseAddress(buf) {
                memset(base, Int32((i / Int(fps)) * 20 % 250), CVPixelBufferGetDataSize(buf))
            }
            CVPixelBufferUnlockBaseAddress(buf, [])
            adaptor.append(buf, withPresentationTime: CMTime(value: CMTimeValue(i), timescale: fps))
        }
        input.markAsFinished()
        await writer.finishWriting()
        XCTAssertEqual(writer.status, .completed)
        return url
    }

    /// A deterministic noise JPEG. Noise compresses badly, so a few of these tile into sheets that are large
    /// enough to push a many-Moment Story past the 16 MB payload ceiling.
    static func noiseJPEG(seed: UInt64, width: Int = 768, height: Int = 432, quality: CGFloat = 0.6) -> Data {
        var s = seed &* 6364136223846793005 &+ 1442695040888963407
        var px = [UInt8](repeating: 255, count: width * height * 4)
        for i in stride(from: 0, to: px.count, by: 4) {
            s ^= s << 13; s ^= s >> 7; s ^= s << 17
            px[i] = UInt8(truncatingIfNeeded: s); px[i + 1] = UInt8(truncatingIfNeeded: s >> 8)
            px[i + 2] = UInt8(truncatingIfNeeded: s >> 16)
        }
        let cs = CGColorSpaceCreateDeviceRGB()
        let img = px.withUnsafeMutableBytes { raw -> CGImage? in
            CGContext(data: raw.baseAddress, width: width, height: height, bitsPerComponent: 8,
                      bytesPerRow: width * 4, space: cs,
                      bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)?.makeImage()
        }
        return UIImage(cgImage: img!).jpegData(compressionQuality: quality)!
    }

    /// A tiny flat JPEG, for fast cache-hit fixtures where only the plumbing matters.
    static func tinyJPEG(gray: CGFloat = 0.5) -> Data {
        UIGraphicsImageRenderer(size: CGSize(width: 64, height: 36)).jpegData(withCompressionQuality: 0.6) { ctx in
            UIColor(white: gray, alpha: 1).setFill(); ctx.fill(CGRect(x: 0, y: 0, width: 64, height: 36))
        }
    }
}
