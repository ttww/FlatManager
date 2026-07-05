import type { FormEvent } from "react";
import { Fragment, useEffect, useState } from "react";

import { QrModal } from "../components/QrModal";
import { api } from "../lib/api";
import { guestUrl } from "../lib/guestUrl";
import { getAdminToken } from "../lib/session";
import type {
    AccessCodeSummary,
    AdminDevice,
    ApartmentImage,
    ApartmentTimezone,
    ApartmentUpdatePayload,
} from "../types";

type ApartmentSummary = {
  apartmentId: string;
  timezone: string;
  addressLine1: string;
  addressLine2: string;
  postalCode: string;
  city: string;
  countryCode: string;
  latitude: string;
  longitude: string;
  hasGuestBackground: boolean;
  guestBackgroundImageId: number | null;
  galleryCount: number;
  deviceCount: number;
  codeCount: number;
  activeCodeCount: number;
};

const MAX_GUEST_BACKGROUND_BYTES = 5 * 1024 * 1024;

function summarizeApartments(
  apartments: ApartmentTimezone[],
  devices: AdminDevice[],
  codes: AccessCodeSummary[],
): ApartmentSummary[] {
  const byApartment = new Map<string, ApartmentSummary>();

  for (const apartment of apartments) {
    byApartment.set(apartment.apartment_id, {
      apartmentId: apartment.apartment_id,
      timezone: apartment.timezone,
      addressLine1: apartment.address_line1 ?? "",
      addressLine2: apartment.address_line2 ?? "",
      postalCode: apartment.postal_code ?? "",
      city: apartment.city ?? "",
      countryCode: apartment.country_code ?? "",
      latitude: apartment.latitude != null ? String(apartment.latitude) : "",
      longitude: apartment.longitude != null ? String(apartment.longitude) : "",
      hasGuestBackground: apartment.has_guest_background ?? false,
      guestBackgroundImageId: apartment.guest_background_image_id ?? null,
      galleryCount: apartment.gallery_count ?? 0,
      deviceCount: 0,
      codeCount: 0,
      activeCodeCount: 0,
    });
  }

  for (const device of devices) {
    const current = byApartment.get(device.apartment_id);
    if (!current) {
      continue;
    }
    current.deviceCount += 1;
    byApartment.set(device.apartment_id, current);
  }

  for (const code of codes) {
    const current = byApartment.get(code.apartment_id);
    if (!current) {
      continue;
    }
    current.codeCount += 1;
    if (code.active) {
      current.activeCodeCount += 1;
    }
    byApartment.set(code.apartment_id, current);
  }

  return [...byApartment.values()].sort((left, right) => left.apartmentId.localeCompare(right.apartmentId));
}

function withAdminToken(url: string, adminToken: string): string {
  try {
    const parsed = new URL(url, window.location.origin);
    parsed.searchParams.set("admin_token", adminToken);
    return parsed.toString();
  } catch {
    const separator = url.includes("?") ? "&" : "?";
    return `${url}${separator}admin_token=${encodeURIComponent(adminToken)}`;
  }
}

export function ApartmentsPage() {
  const adminToken = getAdminToken();
  const [apartments, setApartments] = useState<ApartmentSummary[]>([]);
  const [newApartmentId, setNewApartmentId] = useState("");
  const [newTimezone, setNewTimezone] = useState("UTC");
  const [newAddressLine1, setNewAddressLine1] = useState("");
  const [newAddressLine2, setNewAddressLine2] = useState("");
  const [newPostalCode, setNewPostalCode] = useState("");
  const [newCity, setNewCity] = useState("");
  const [newCountryCode, setNewCountryCode] = useState("");
  const [newLatitude, setNewLatitude] = useState("");
  const [newLongitude, setNewLongitude] = useState("");
  const [creatingApartment, setCreatingApartment] = useState(false);
  const [editingApartmentId, setEditingApartmentId] = useState<string | null>(null);
  const [editingForm, setEditingForm] = useState<ApartmentUpdatePayload>({ timezone: "UTC" });
  const [savingTimezone, setSavingTimezone] = useState(false);
  const [deletingApartmentId, setDeletingApartmentId] = useState<string | null>(null);
  const [uploadingBackgroundApartmentId, setUploadingBackgroundApartmentId] = useState<string | null>(null);
  const [removingBackgroundApartmentId, setRemovingBackgroundApartmentId] = useState<string | null>(null);
  const [imagesByApartment, setImagesByApartment] = useState<Record<string, ApartmentImage[]>>({});
  const [expandedGalleryApartmentId, setExpandedGalleryApartmentId] = useState<string | null>(null);
  const [reorderingApartmentId, setReorderingApartmentId] = useState<string | null>(null);
  const [deletingImageId, setDeletingImageId] = useState<number | null>(null);
  const [settingBackgroundImageId, setSettingBackgroundImageId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [qrApartmentId, setQrApartmentId] = useState<string | null>(null);

  const load = async (cancelled?: { value: boolean }) => {
    try {
      const [apartmentRows, devices, codes] = await Promise.all([
        api.listApartmentTimezones(getAdminToken()),
        api.listDevices(getAdminToken()),
        api.listAccessCodes(getAdminToken()),
      ]);

      if (!cancelled || !cancelled.value) {
        setApartments(summarizeApartments(apartmentRows, devices, codes));
        setMessage("");
      }
    } catch (error) {
      if (!cancelled || !cancelled.value) {
        setMessage(error instanceof Error ? error.message : "Failed to load apartments.");
      }
    }
  };

  useEffect(() => {
    const cancelled = { value: false };
    const timerId = window.setTimeout(() => {
      void load(cancelled);
    }, 0);

    return () => {
      cancelled.value = true;
      window.clearTimeout(timerId);
    };
  }, []);

  const onStartEditTimezone = (apartment: ApartmentSummary) => {
    setEditingApartmentId(apartment.apartmentId);
    setEditingForm({
      timezone: apartment.timezone || "UTC",
      address_line1: apartment.addressLine1,
      address_line2: apartment.addressLine2,
      postal_code: apartment.postalCode,
      city: apartment.city,
      country_code: apartment.countryCode,
      latitude: apartment.latitude ? Number.parseFloat(apartment.latitude) : null,
      longitude: apartment.longitude ? Number.parseFloat(apartment.longitude) : null,
    });
    setMessage("");
  };

  const onCancelEditTimezone = () => {
    setEditingApartmentId(null);
    setEditingForm({ timezone: "UTC" });
  };

  const onSaveTimezone = async (apartmentId: string) => {
    const timezone = (editingForm.timezone ?? "").trim();
    if (!timezone) {
      setMessage("Timezone cannot be empty.");
      return;
    }

    setSavingTimezone(true);
    setMessage("");
    try {
      await api.updateApartment(getAdminToken(), apartmentId, {
        ...editingForm,
        timezone,
        address_line1: (editingForm.address_line1 ?? "").trim() || null,
        address_line2: (editingForm.address_line2 ?? "").trim() || null,
        postal_code: (editingForm.postal_code ?? "").trim() || null,
        city: (editingForm.city ?? "").trim() || null,
        country_code: (editingForm.country_code ?? "").trim() || null,
        latitude:
          editingForm.latitude == null || Number.isNaN(editingForm.latitude)
            ? null
            : editingForm.latitude,
        longitude:
          editingForm.longitude == null || Number.isNaN(editingForm.longitude)
            ? null
            : editingForm.longitude,
      });
      onCancelEditTimezone();
      await load();
      setMessage(`Apartment metadata updated for ${apartmentId}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Apartment update failed.");
    } finally {
      setSavingTimezone(false);
    }
  };

  const onCreateApartment = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const apartmentId = newApartmentId.trim();
    const timezone = newTimezone.trim();

    if (!apartmentId) {
      setMessage("Apartment ID is required.");
      return;
    }

    if (!timezone) {
      setMessage("Timezone is required.");
      return;
    }

    const latitude = newLatitude.trim() ? Number.parseFloat(newLatitude.trim()) : null;
    const longitude = newLongitude.trim() ? Number.parseFloat(newLongitude.trim()) : null;
    if (latitude != null && Number.isNaN(latitude)) {
      setMessage("Latitude must be a valid number.");
      return;
    }
    if (longitude != null && Number.isNaN(longitude)) {
      setMessage("Longitude must be a valid number.");
      return;
    }

    setCreatingApartment(true);
    setMessage("");
    try {
      await api.createApartment(getAdminToken(), {
        apartment_id: apartmentId,
        timezone,
        address_line1: newAddressLine1.trim() || null,
        address_line2: newAddressLine2.trim() || null,
        postal_code: newPostalCode.trim() || null,
        city: newCity.trim() || null,
        country_code: newCountryCode.trim() || null,
        latitude,
        longitude,
      });
      setNewApartmentId("");
      setNewTimezone("UTC");
      setNewAddressLine1("");
      setNewAddressLine2("");
      setNewPostalCode("");
      setNewCity("");
      setNewCountryCode("");
      setNewLatitude("");
      setNewLongitude("");
      await load();
      setMessage(`Apartment ${apartmentId} created.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Apartment creation failed.");
    } finally {
      setCreatingApartment(false);
    }
  };

  const onDeleteApartment = async (apartmentId: string) => {
    if (!window.confirm(`Delete apartment ${apartmentId}?`)) {
      return;
    }

    setDeletingApartmentId(apartmentId);
    setMessage("");
    try {
      await api.deleteApartment(getAdminToken(), apartmentId);
      if (editingApartmentId === apartmentId) {
        onCancelEditTimezone();
      }
      await load();
      setMessage(`Apartment ${apartmentId} deleted.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Apartment delete failed.");
    } finally {
      setDeletingApartmentId(null);
    }
  };

  const onUploadGuestBackground = async (apartmentId: string, file: File | null) => {
    if (!file) {
      return;
    }

    if (file.size > MAX_GUEST_BACKGROUND_BYTES) {
      setMessage("Image is too large. Maximum allowed size is 5 MB.");
      return;
    }

    setUploadingBackgroundApartmentId(apartmentId);
    setMessage("");
    try {
      await api.uploadApartmentImage(getAdminToken(), apartmentId, file);
      await load();
      if (expandedGalleryApartmentId === apartmentId) {
        const rows = await api.listApartmentImages(getAdminToken(), apartmentId);
        setImagesByApartment((prev) => ({ ...prev, [apartmentId]: rows }));
      }
      setMessage(`Image uploaded for ${apartmentId}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Image upload failed.");
    } finally {
      setUploadingBackgroundApartmentId(null);
    }
  };

  const onDeleteGuestBackground = async (apartmentId: string) => {
    setRemovingBackgroundApartmentId(apartmentId);
    setMessage("");
    try {
      await api.deleteApartmentGuestBackground(getAdminToken(), apartmentId);
      await load();
      setMessage(`Guest background removed for ${apartmentId}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Guest background removal failed.");
    } finally {
      setRemovingBackgroundApartmentId(null);
    }
  };

  const loadApartmentImages = async (apartmentId: string) => {
    const rows = await api.listApartmentImages(getAdminToken(), apartmentId);
    setImagesByApartment((prev) => ({ ...prev, [apartmentId]: rows }));
  };

  const onToggleGallery = async (apartmentId: string) => {
    if (expandedGalleryApartmentId === apartmentId) {
      setExpandedGalleryApartmentId(null);
      return;
    }
    setExpandedGalleryApartmentId(apartmentId);
    try {
      await loadApartmentImages(apartmentId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to load apartment images.");
    }
  };

  const persistImageOrder = async (apartmentId: string, images: ApartmentImage[]) => {
    setReorderingApartmentId(apartmentId);
    try {
      const items = images.map((image, index) => ({ image_id: image.id, sort_order: index + 1 }));
      const updated = await api.reorderApartmentImages(getAdminToken(), apartmentId, items);
      setImagesByApartment((prev) => ({ ...prev, [apartmentId]: updated }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Image reorder failed.");
      await loadApartmentImages(apartmentId);
    } finally {
      setReorderingApartmentId(null);
    }
  };

  const onMoveImage = async (apartmentId: string, imageId: number, direction: -1 | 1) => {
    const current = imagesByApartment[apartmentId] ?? [];
    const index = current.findIndex((image) => image.id === imageId);
    if (index < 0) return;

    const swapIndex = index + direction;
    if (swapIndex < 0 || swapIndex >= current.length) return;

    const reordered = [...current];
    const temp = reordered[index];
    reordered[index] = reordered[swapIndex];
    reordered[swapIndex] = temp;
    setImagesByApartment((prev) => ({ ...prev, [apartmentId]: reordered }));
    await persistImageOrder(apartmentId, reordered);
  };

  const onSetGuestBackgroundImage = async (apartmentId: string, imageId: number) => {
    setSettingBackgroundImageId(imageId);
    setMessage("");
    try {
      await api.setApartmentGuestBackgroundImage(getAdminToken(), apartmentId, imageId);
      await load();
      await loadApartmentImages(apartmentId);
      setMessage(`Guest background updated for ${apartmentId}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to set guest background image.");
    } finally {
      setSettingBackgroundImageId(null);
    }
  };

  const onDeleteImage = async (apartmentId: string, imageId: number) => {
    setDeletingImageId(imageId);
    setMessage("");
    try {
      await api.deleteApartmentImage(getAdminToken(), apartmentId, imageId);
      await load();
      await loadApartmentImages(apartmentId);
      setMessage("Image deleted.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Image delete failed.");
    } finally {
      setDeletingImageId(null);
    }
  };

  return (
    <section className="panel">
      <header className="panel-header">
        <h2>Apartments</h2>
        <p>Create and edit apartments in one place, then assign devices and access codes to them.</p>
      </header>

      <form className="device-form" onSubmit={onCreateApartment}>
        <input
          value={newApartmentId}
          onChange={(event) => setNewApartmentId(event.target.value)}
          placeholder="Apartment ID"
          required
        />
        <input
          value={newTimezone}
          onChange={(event) => setNewTimezone(event.target.value)}
          placeholder="Timezone (IANA, e.g. Europe/Berlin)"
          required
        />
        <input
          value={newAddressLine1}
          onChange={(event) => setNewAddressLine1(event.target.value)}
          placeholder="Address line 1"
        />
        <input
          value={newAddressLine2}
          onChange={(event) => setNewAddressLine2(event.target.value)}
          placeholder="Address line 2"
        />
        <input
          value={newPostalCode}
          onChange={(event) => setNewPostalCode(event.target.value)}
          placeholder="Postal code"
        />
        <input
          value={newCity}
          onChange={(event) => setNewCity(event.target.value)}
          placeholder="City"
        />
        <input
          value={newCountryCode}
          onChange={(event) => setNewCountryCode(event.target.value.toUpperCase())}
          placeholder="Country code (DE)"
          maxLength={2}
        />
        <input
          value={newLatitude}
          onChange={(event) => setNewLatitude(event.target.value)}
          placeholder="Latitude"
        />
        <input
          value={newLongitude}
          onChange={(event) => setNewLongitude(event.target.value)}
          placeholder="Longitude"
        />
        <button type="submit" className="primary-button" disabled={creatingApartment}>
          {creatingApartment ? "Creating..." : "Create Apartment"}
        </button>
      </form>

      {message ? <p className="inline-message">{message}</p> : null}

      {apartments.length === 0 && !message ? (
        <p className="inline-message">No apartments found yet. Create your first apartment above.</p>
      ) : null}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Apartment</th>
              <th>Timezone</th>
              <th>Address</th>
              <th>Geo</th>
              <th>Images</th>
              <th>Devices</th>
              <th>Access Codes</th>
              <th>Active Codes</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {apartments.map((apartment) => (
              <Fragment key={apartment.apartmentId}>
                <tr>
                <td>{apartment.apartmentId}</td>
                <td>
                  {editingApartmentId === apartment.apartmentId ? (
                    <div>
                      <input
                        value={editingForm.timezone ?? ""}
                        onChange={(event) =>
                          setEditingForm((prev) => ({ ...prev, timezone: event.target.value }))
                        }
                        placeholder="Europe/Berlin"
                      />
                    </div>
                  ) : (
                    apartment.timezone
                  )}
                </td>
                <td>
                  {editingApartmentId === apartment.apartmentId ? (
                    <div>
                      <input
                        value={editingForm.address_line1 ?? ""}
                        onChange={(event) =>
                          setEditingForm((prev) => ({ ...prev, address_line1: event.target.value }))
                        }
                        placeholder="Address line 1"
                      />
                      <input
                        value={editingForm.address_line2 ?? ""}
                        onChange={(event) =>
                          setEditingForm((prev) => ({ ...prev, address_line2: event.target.value }))
                        }
                        placeholder="Address line 2"
                      />
                      <input
                        value={editingForm.postal_code ?? ""}
                        onChange={(event) =>
                          setEditingForm((prev) => ({ ...prev, postal_code: event.target.value }))
                        }
                        placeholder="Postal code"
                      />
                      <input
                        value={editingForm.city ?? ""}
                        onChange={(event) =>
                          setEditingForm((prev) => ({ ...prev, city: event.target.value }))
                        }
                        placeholder="City"
                      />
                      <input
                        value={editingForm.country_code ?? ""}
                        maxLength={2}
                        onChange={(event) =>
                          setEditingForm((prev) => ({
                            ...prev,
                            country_code: event.target.value.toUpperCase(),
                          }))
                        }
                        placeholder="Country"
                      />
                    </div>
                  ) : (
                    <span>
                      {[
                        apartment.addressLine1,
                        apartment.addressLine2,
                        apartment.postalCode,
                        apartment.city,
                        apartment.countryCode,
                      ]
                        .filter(Boolean)
                        .join(", ") || "-"}
                    </span>
                  )}
                </td>
                <td>
                  {editingApartmentId === apartment.apartmentId ? (
                    <div>
                      <input
                        value={editingForm.latitude == null ? "" : String(editingForm.latitude)}
                        onChange={(event) =>
                          setEditingForm((prev) => ({
                            ...prev,
                            latitude: event.target.value ? Number.parseFloat(event.target.value) : null,
                          }))
                        }
                        placeholder="Latitude"
                      />
                      <input
                        value={editingForm.longitude == null ? "" : String(editingForm.longitude)}
                        onChange={(event) =>
                          setEditingForm((prev) => ({
                            ...prev,
                            longitude: event.target.value ? Number.parseFloat(event.target.value) : null,
                          }))
                        }
                        placeholder="Longitude"
                      />
                    </div>
                  ) : (
                    <span>
                      {apartment.latitude && apartment.longitude
                        ? `${apartment.latitude}, ${apartment.longitude}`
                        : "-"}
                    </span>
                  )}
                </td>
                <td>{apartment.galleryCount}</td>
                <td>{apartment.deviceCount}</td>
                <td>{apartment.codeCount}</td>
                <td>{apartment.activeCodeCount}</td>
                <td>
                  <div className="row-actions">
                    {editingApartmentId === apartment.apartmentId ? (
                      <>
                        <button
                          type="button"
                          onClick={() => void onSaveTimezone(apartment.apartmentId)}
                          disabled={savingTimezone || deletingApartmentId === apartment.apartmentId}
                        >
                          {savingTimezone ? "Saving..." : "Save"}
                        </button>
                        <button
                          type="button"
                          onClick={onCancelEditTimezone}
                          disabled={savingTimezone || deletingApartmentId === apartment.apartmentId}
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => onStartEditTimezone(apartment)}
                          title="Edit apartment timezone"
                          disabled={deletingApartmentId === apartment.apartmentId}
                        >
                          Edit
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      onClick={() => setQrApartmentId(apartment.apartmentId)}
                      title="Show guest QR code"
                      disabled={
                        deletingApartmentId === apartment.apartmentId ||
                        uploadingBackgroundApartmentId === apartment.apartmentId ||
                        removingBackgroundApartmentId === apartment.apartmentId
                      }
                    >
                      QR Code
                    </button>
                    <button
                      type="button"
                      onClick={() => void onToggleGallery(apartment.apartmentId)}
                      disabled={deletingApartmentId === apartment.apartmentId}
                    >
                      {expandedGalleryApartmentId === apartment.apartmentId ? "Hide Gallery" : "Gallery"}
                    </button>
                    <label>
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        onChange={(event) =>
                          void onUploadGuestBackground(apartment.apartmentId, event.target.files?.[0] ?? null)
                        }
                        disabled={
                          deletingApartmentId === apartment.apartmentId ||
                          uploadingBackgroundApartmentId === apartment.apartmentId ||
                          removingBackgroundApartmentId === apartment.apartmentId
                        }
                      />
                    </label>
                    {apartment.hasGuestBackground ? (
                      <button
                        type="button"
                        onClick={() => void onDeleteGuestBackground(apartment.apartmentId)}
                        disabled={
                          deletingApartmentId === apartment.apartmentId ||
                          uploadingBackgroundApartmentId === apartment.apartmentId ||
                          removingBackgroundApartmentId === apartment.apartmentId
                        }
                      >
                        {removingBackgroundApartmentId === apartment.apartmentId ? "Removing image..." : "Remove Image"}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="danger"
                      onClick={() => void onDeleteApartment(apartment.apartmentId)}
                      disabled={
                        savingTimezone ||
                        deletingApartmentId === apartment.apartmentId ||
                        uploadingBackgroundApartmentId === apartment.apartmentId ||
                        removingBackgroundApartmentId === apartment.apartmentId
                      }
                    >
                      {deletingApartmentId === apartment.apartmentId ? "Deleting..." : "Delete"}
                    </button>
                  </div>
                </td>
                </tr>
                {expandedGalleryApartmentId === apartment.apartmentId ? (
                <tr key={`${apartment.apartmentId}-gallery`}>
                  <td colSpan={10}>
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Preview</th>
                            <th>Filename</th>
                            <th>Order</th>
                            <th>Background</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(imagesByApartment[apartment.apartmentId] ?? []).map((image, index, all) => (
                            <tr key={image.id}>
                              <td className="gallery-cell">
                                <img
                                  src={withAdminToken(image.image_url, adminToken)}
                                  alt={image.original_filename}
                                  className="gallery-thumb"
                                />
                                <div className="gallery-hover-preview" role="tooltip" aria-hidden="true">
                                  <img
                                    src={withAdminToken(image.image_url, adminToken)}
                                    alt={image.original_filename}
                                    className="gallery-hover-image"
                                  />
                                </div>
                              </td>
                              <td>{image.original_filename}</td>
                              <td>{index + 1}</td>
                              <td>{image.is_guest_background ? "Yes" : "No"}</td>
                              <td>
                                <div className="row-actions">
                                  <button
                                    type="button"
                                    onClick={() => void onMoveImage(apartment.apartmentId, image.id, -1)}
                                    disabled={index === 0 || reorderingApartmentId === apartment.apartmentId}
                                  >
                                    Up
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => void onMoveImage(apartment.apartmentId, image.id, 1)}
                                    disabled={
                                      index === all.length - 1 || reorderingApartmentId === apartment.apartmentId
                                    }
                                  >
                                    Down
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => void onSetGuestBackgroundImage(apartment.apartmentId, image.id)}
                                    disabled={
                                      image.is_guest_background || settingBackgroundImageId === image.id
                                    }
                                  >
                                    {settingBackgroundImageId === image.id ? "Saving..." : "Set Background"}
                                  </button>
                                  <button
                                    type="button"
                                    className="danger"
                                    onClick={() => void onDeleteImage(apartment.apartmentId, image.id)}
                                    disabled={deletingImageId === image.id}
                                  >
                                    {deletingImageId === image.id ? "Deleting..." : "Delete"}
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </td>
                </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {qrApartmentId ? (
        <QrModal
          url={guestUrl(qrApartmentId)}
          apartmentId={qrApartmentId}
          onClose={() => setQrApartmentId(null)}
        />
      ) : null}
    </section>
  );
}