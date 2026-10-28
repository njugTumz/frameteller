/** The microphones the browser can record from. Labels are empty until the page may use the microphone. */
export interface AudioInput {
  deviceId: string
  label: string
}

export async function listAudioInputs(media: MediaDevices | undefined = navigator.mediaDevices): Promise<AudioInput[]> {
  if (!media?.enumerateDevices) return []
  const devices = await media.enumerateDevices().catch(() => [] as MediaDeviceInfo[])
  return devices
    .filter((d) => d.kind === 'audioinput' && d.deviceId)
    .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `Microphone ${i + 1}` }))
}
