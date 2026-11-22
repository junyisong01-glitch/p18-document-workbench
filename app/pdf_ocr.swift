import Foundation
import Vision

struct TextLine: Encodable {
    let text: String
    let confidence: Float
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "en-US"]
request.usesLanguageCorrection = false
let image = URL(fileURLWithPath: CommandLine.arguments[1])
do {
    try VNImageRequestHandler(url: image).perform([request])
    let lines = (request.results ?? []).compactMap { observation -> TextLine? in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        return TextLine(text: candidate.string, confidence: candidate.confidence)
    }
    let encoded = try JSONEncoder().encode(lines)
    FileHandle.standardOutput.write(encoded)
} catch {
    FileHandle.standardError.write(Data(String(reflecting: error).utf8))
    exit(EXIT_FAILURE)
}
