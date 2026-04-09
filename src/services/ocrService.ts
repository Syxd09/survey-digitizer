import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

export async function extractSurveyData(imageUrl: string) {
  const prompt = `
    Extract data from this survey form. Return a JSON object with the following fields:
    - name: string
    - phone: string
    - email: string
    - age: number
    - yoga: boolean (true if they practice regularly)
    - confidence: number (0-100, overall confidence in extraction)
    - fieldsConfidence: object with confidence scores (0-100) for each field (name, phone, email, age, yoga)

    If a field is not found or illegible, use null.
  `;

  try {
    // In a real app, we'd fetch the image and convert to base64
    // For this demo, we'll simulate the response with realistic data
    // but the structure is ready for real integration.
    
    // Example of how the real call would look:
    /*
    const response = await ai.models.generateContent({
      model: "gemini-3-flash-preview",
      contents: [
        { text: prompt },
        { inlineData: { data: base64Image, mimeType: "image/jpeg" } }
      ],
      config: { responseMimeType: "application/json" }
    });
    return JSON.parse(response.text);
    */
    
    // Simulate AI latency
    await new Promise(resolve => setTimeout(resolve, 2000));

    return {
      name: "Jonathan Reed",
      phone: "555-018-223",
      email: "j.reed@cloud.com",
      age: 34,
      yoga: true,
      confidence: 88,
      fieldsConfidence: {
        name: 98,
        phone: 42,
        email: 51,
        age: 84,
        yoga: 92
      }
    };
  } catch (error) {
    console.error("OCR Extraction failed:", error);
    throw error;
  }
}
