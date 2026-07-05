export type DeviceStatus = {
  id: number;
  apartment_id: string;
  apartment_timezone: string;
  device_name: string;
  status: string;
  last_seen: string | null;
  last_seen_seconds_ago: number | null;
  last_ip: string | null;
};

export type CommandSummary = {
  id: number;
  apartment_id: string;
  apartment_timezone: string;
  device_id: number;
  command: string;
  status: string;
  duration_ms: number;
  created_at: string;
  expires_at: string;
  delivered_at: string | null;
  acknowledged_at: string | null;
};

export type AccessLogSummary = {
  id: number;
  apartment_id: string;
  apartment_timezone: string;
  timestamp: string;
  ip_address: string;
  result: string;
  reason: string | null;
  command_id: number | null;
  access_code_id: number | null;
};

export type AdminDevice = {
  id: number;
  apartment_id: string;
  apartment_timezone: string;
  device_name: string;
  status: string;
  last_seen: string | null;
  last_ip: string | null;
  created_at: string;
  updated_at: string;
};

export type NewDeviceResponse = {
  id: number;
  apartment_id: string;
  device_name: string;
  raw_token: string;
  created_at: string;
};

export type RotateDeviceTokenResponse = {
  id: number;
  raw_token: string;
  updated_at: string;
};

export type DeviceUpdatePayload = {
  apartment_id?: string;
  device_name?: string;
};

export type AccessCodeForm = {
  apartment_id: string;
  code: string;
  valid_from: string;
  valid_until: string;
  input_timezone?: string;
  max_uses: number;
  booking_reference?: string;
  guest_name?: string;
};

export type AccessCodeSummary = {
  id: number;
  apartment_id: string;
  apartment_timezone: string;
  valid_from: string;
  valid_until: string;
  max_uses: number;
  used_count: number;
  active: boolean;
  booking_reference: string | null;
  guest_name: string | null;
  created_at: string;
  updated_at: string;
};

export type ApartmentTimezone = {
  apartment_id: string;
  timezone: string;
  address_line1?: string | null;
  address_line2?: string | null;
  postal_code?: string | null;
  city?: string | null;
  country_code?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  has_guest_background?: boolean;
  guest_background_image_id?: number | null;
  gallery_count?: number;
};

export type ApartmentImage = {
  id: number;
  apartment_id: string;
  original_filename: string;
  content_type: string;
  byte_size: number;
  sort_order: number;
  image_url: string;
  is_guest_background: boolean;
  created_at: string;
  updated_at: string;
};

export type ApartmentImageBulkUploadResult = {
  uploaded: ApartmentImage[];
  skipped_existing: ApartmentImage[];
};

export type ApartmentUpdatePayload = {
  timezone?: string;
  address_line1?: string | null;
  address_line2?: string | null;
  postal_code?: string | null;
  city?: string | null;
  country_code?: string | null;
  latitude?: number | null;
  longitude?: number | null;
};
