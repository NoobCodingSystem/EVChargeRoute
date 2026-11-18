
import React, { useState } from "react";
import {
  Card,
  Row,
  Col,
  Form,
  Button,
  Alert,
  Badge,
  InputGroup
} from "react-bootstrap";

import {
  FaCar,
  FaBolt,
  FaRoute,
  FaGaugeHigh,
  FaDatabase
} from "react-icons/fa6";

import { api } from "../api";

export default function Dashboard({
  profile,
  setProfile,
  vehicles,
  ownerId,
  setOwnerId,
  setPremium,
  onSaved,
  setTab
}) {
  const [lookupEmail, setLookupEmail] = useState("");
  const [lookupMessage, setLookupMessage] = useState("");
  const [otp, setOtp] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [verifiedEmail, setVerifiedEmail] = useState("");
  const [telemetry, setTelemetry] = useState(null);

  const update = (key, value) => {
    setProfile(previous => ({
      ...previous,
      [key]: value
    }));
  };

  const v = vehicles[profile.vehicle];

  const currentEmail = profile.ownerEmail.trim().toLowerCase();

  const isVerified =
    currentEmail !== "" &&
    verifiedEmail === currentEmail;

  // Request OTP voluntarily.
  const sendOtp = async () => {
    try {
      await api("/api/auth/request-otp", {
        method: "POST",
        body: JSON.stringify({
          email: profile.ownerEmail
        })
      });

      setOtpSent(true);
      setLookupMessage(
        "Verification code sent. Check your inbox and spam folder."
      );
    } catch (err) {
      setLookupMessage(err.message);
    }
  };

  // Verify the entered OTP.
  const verifyOtp = async () => {
    try {
      await api("/api/auth/verify-otp", {
        method: "POST",
        body: JSON.stringify({
          email: profile.ownerEmail,
          otp
        })
      });

      setVerifiedEmail(currentEmail);
      setLookupMessage(
        "Email verified successfully. You can now access existing profile data."
      );
    } catch (err) {
      setLookupMessage(err.message);
    }
  };

  // Save a profile.
  // OTP is not required when creating a new profile.
  // Backend requires OTP if this email already exists.
  const save = async (e) => {
    e.preventDefault();

    try {
      const x = await api("/api/profile", {
        method: "POST",
        body: JSON.stringify({
          owner_name: profile.ownerName,
          email: profile.ownerEmail,
          vehicle_id: profile.vehicle,
          registration: profile.registration,
          battery_pct: Number(profile.charge),
          personal_range_km: profile.personalRange
            ? Number(profile.personalRange)
            : null
        })
      });

      setOwnerId(x.id);

      setLookupMessage(
        "Profile saved successfully. Email verification status: " +
        (isVerified ? "Verified." : "Not verified.")
      );

      onSaved();
      setTab("planner");

    } catch (err) {
      setLookupMessage(err.message);
    }
  };

  // Load an existing profile.
  // OTP remains mandatory for protecting saved owner information.
  const load = async () => {
    if (!isVerified) {
      setLookupMessage(
        "Please verify your email before loading an existing profile."
      );
      return;
    }

    try {
      const x = await api(
        `/api/profile?email=${encodeURIComponent(lookupEmail)}`
      );

      setProfile({
        ownerName: x.owner_name,
        ownerEmail: x.email,
        vehicle: x.vehicle_id,
        registration: x.registration || "",
        charge: x.battery_pct,
        personalRange: x.personal_range_km ?? ""
      });

      setOwnerId(x.id);

      setLookupMessage(
        "Saved profile loaded successfully."
      );

    } catch (err) {
      setLookupMessage(err.message);
    }
  };

  // Private vehicle telemetry remains OTP-protected.
  const refreshTelemetry = async () => {
    if (!isVerified) {
      setLookupMessage(
        "Verify your email before accessing vehicle telemetry."
      );
      return;
    }

    try {
      const x = await api(
        `/api/telemetry?email=${encodeURIComponent(profile.ownerEmail)}`
      );

      setTelemetry(x.telemetry);

      if (x.telemetry) {
        setProfile(previous => ({
          ...previous,
          charge: x.telemetry.battery_pct ?? previous.charge,
          personalRange:
            x.telemetry.range_km ?? previous.personalRange
        }));

        setLookupMessage("Latest vehicle telemetry loaded.");

      } else {
        setLookupMessage(
          "No vehicle telemetry has been received yet."
        );
      }

    } catch (err) {
      setLookupMessage(err.message);
    }
  };

  return (
    <div className="page">

      {/* HERO SECTION */}
      <div className="hero rounded-4 p-4 p-lg-5 mb-4">

        <Row className="align-items-center g-4">

          <Col lg={7}>

            <Badge bg="light" text="primary" className="mb-3">
              PERSONAL EV ROUTING
            </Badge>

            <h1 className="display-5 fw-bold">
              Real roads.{" "}
              <span>Personalized EV planning.</span>
            </h1>

            <p className="lead text-secondary">
              Search places like a maps app, calculate the actual road
              route, inspect charger records and adapt range calculations
              to the owner's EV.
            </p>

            <Button
              size="lg"
              onClick={() => setTab("planner")}
              disabled={!ownerId}
            >
              Plan a journey →
            </Button>

          </Col>

          <Col lg={5}>

            <div className="glass-card p-4">

              <div className="small text-secondary">
                CURRENT VEHICLE
              </div>

              <h4>{v?.name || "Choose a vehicle"}</h4>

              <div className="d-flex justify-content-between mt-3">
                <span>Battery</span>
                <strong>{profile.charge}%</strong>
              </div>

              <div className="progress mt-2">
                <div
                  className="progress-bar"
                  style={{
                    width: `${Math.max(
                      0,
                      Math.min(100, profile.charge)
                    )}%`
                  }}
                />
              </div>

            </div>

          </Col>

        </Row>

      </div>

      <Row className="g-4">

        {/* PROFILE FORM */}
        <Col lg={8}>

          <Card className="shadow-sm border-0">

            <Card.Body className="p-4">

              <h3>Owner & Vehicle Profile</h3>

              <p className="text-secondary">
                Create a new EV profile without email verification.
                Verification is required only when accessing an existing
                profile or private vehicle telemetry.
              </p>

              <Form onSubmit={save}>

                <Row className="g-3">

                  <Col md={6}>

                    <Form.Label>Owner name</Form.Label>

                    <Form.Control
                      required
                      value={profile.ownerName}
                      onChange={e =>
                        update("ownerName", e.target.value)
                      }
                      placeholder="Your name"
                    />

                  </Col>

                  <Col md={6}>

                    <Form.Label>Email / account ID</Form.Label>

                    <Form.Control
                      required
                      type="email"
                      value={profile.ownerEmail}
                      onChange={e => {
                        update("ownerEmail", e.target.value);
                        setOtp("");
                        setOtpSent(false);
                      }}
                      placeholder="you@example.com"
                    />

                  </Col>

                  {/* OPTIONAL EMAIL VERIFICATION */}
                  <Col md={12}>

                    <Card className="border">

                      <Card.Body>

                        <div className="d-flex justify-content-between align-items-center mb-2">

                          <h5 className="mb-0">
                            Email Verification
                          </h5>

                          {isVerified ? (
                            <Badge bg="success">
                              Verified
                            </Badge>
                          ) : (
                            <Badge bg="secondary">
                              Optional
                            </Badge>
                          )}

                        </div>

                        <p className="small text-secondary mb-3">
                          Email verification is optional when creating
                          a new profile. You can verify your email
                          voluntarily using a 6-digit OTP.
                        </p>

                        <InputGroup>

                          <Form.Control
                            type="text"
                            value={otp}
                            onChange={e =>
                              setOtp(
                                e.target.value
                                  .replace(/\D/g, "")
                                  .slice(0, 6)
                              )
                            }
                            placeholder="Enter 6-digit OTP"
                            disabled={!otpSent || isVerified}
                          />

                          <Button
                            type="button"
                            variant="outline-primary"
                            onClick={sendOtp}
                            disabled={
                              !profile.ownerEmail.includes("@") ||
                              isVerified
                            }
                          >
                            Send OTP
                          </Button>

                          <Button
                            type="button"
                            variant="outline-success"
                            onClick={verifyOtp}
                            disabled={
                              otp.length !== 6 ||
                              isVerified
                            }
                          >
                            Verify
                          </Button>

                        </InputGroup>

                        <Form.Text>
                          {isVerified
                            ? "Your email is verified for 24 hours."
                            : "You can skip verification when creating a new profile."}
                        </Form.Text>

                      </Card.Body>

                    </Card>

                  </Col>

                  <Col md={6}>

                    <Form.Label>Vehicle model</Form.Label>

                    <Form.Select
                      required
                      value={profile.vehicle}
                      onChange={e =>
                        update("vehicle", e.target.value)
                      }
                    >

                      <option value="">
                        Select your EV
                      </option>

                      {Object.entries(vehicles).map(([id, x]) => (
                        <option key={id} value={id}>
                          {x.name}
                        </option>
                      ))}

                    </Form.Select>

                  </Col>

                  <Col md={6}>

                    <Form.Label>
                      Registration (optional)
                    </Form.Label>

                    <Form.Control
                      value={profile.registration}
                      onChange={e =>
                        update("registration", e.target.value)
                      }
                      placeholder="Vehicle registration"
                    />

                  </Col>

                  <Col md={6}>

                    <Form.Label>
                      Current battery: {profile.charge}%
                    </Form.Label>

                    <Form.Range
                      min="0"
                      max="100"
                      value={profile.charge}
                      onChange={e =>
                        update("charge", Number(e.target.value))
                      }
                    />

                  </Col>

                  <Col md={6}>

                    <Form.Label>
                      Your observed full-charge range (km)
                    </Form.Label>

                    <Form.Control
                      type="number"
                      min="20"
                      max="2000"
                      value={profile.personalRange}
                      onChange={e =>
                        update("personalRange", e.target.value)
                      }
                      placeholder={
                        v
                          ? `Optional; reference ${v.reference_range_km} km`
                          : "Optional"
                      }
                    />

                    <Form.Text>
                      Used with the vehicle reference value to
                      personalize energy estimates.
                    </Form.Text>

                  </Col>

                  <Col>

                    <Button
                      type="submit"
                      className="w-100"
                    >
                      Save Profile & Continue
                    </Button>

                    <div className="small text-secondary text-center mt-2">
                      New profiles can be saved without email OTP.
                    </div>

                  </Col>

                </Row>

              </Form>

            </Card.Body>

          </Card>

        </Col>

        {/* PROFILE LOADING AND VEHICLE INFORMATION */}
        <Col lg={4}>

          <Card className="shadow-sm border-0 h-100">

            <Card.Body className="p-4">

              <h5>
                <FaDatabase className="me-2" />
                Load Saved Profile
              </h5>

              <p className="small text-secondary">
                Enter your previously registered email. OTP
                verification is required to access an existing profile.
              </p>

              <InputGroup>

                <Form.Control
                  type="email"
                  value={lookupEmail}
                  onChange={e => {
                    setLookupEmail(e.target.value);
                    update("ownerEmail", e.target.value);
                    setOtp("");
                    setOtpSent(false);
                  }}
                  placeholder="Saved email"
                />

                <Button
                  variant="outline-primary"
                  onClick={load}
                  disabled={
                    !lookupEmail ||
                    verifiedEmail !== lookupEmail.trim().toLowerCase()
                  }
                >
                  Load
                </Button>

              </InputGroup>

              {lookupMessage && (
                <Alert
                  className="small mt-3"
                  variant={
                    lookupMessage.toLowerCase().includes("success") ||
                      lookupMessage.toLowerCase().includes("loaded") ||
                      lookupMessage.toLowerCase().includes("verified")
                      ? "success"
                      : "warning"
                  }
                >
                  {lookupMessage}
                </Alert>
              )}

              <hr />

              <h5>Vehicle Intelligence</h5>

              <div className="mini-stat">
                <FaCar />
                <span>
                  {v?.battery_kwh ?? "—"} kWh battery
                </span>
              </div>

              <div className="mini-stat">
                <FaGaugeHigh />
                <span>
                  {v?.reference_range_km ?? "—"} km reference range
                </span>
              </div>

              <div className="mini-stat">
                <FaBolt />
                <span>
                  {v?.dc_kw ?? "—"} kW max DC reference
                </span>
              </div>

              <div className="mini-stat">
                <FaRoute />
                <span>
                  {v?.charging_port || "—"}
                </span>
              </div>

              <Alert variant="info" className="small mt-4">
                Range model = vehicle reference data + owner
                observation, with a safety reserve.
              </Alert>

              <Button
                type="button"
                variant="outline-primary"
                className="w-100"
                onClick={refreshTelemetry}
                disabled={!isVerified}
              >
                Refresh Vehicle Telemetry
              </Button>

              {!isVerified && (
                <div className="small text-secondary mt-2">
                  Verify your email to access private vehicle telemetry.
                </div>
              )}

              {telemetry && (
                <div className="small mt-2 text-secondary">
                  Last update: {telemetry.updated_at}
                  <br />
                  Odometer: {telemetry.odometer_km ?? "—"} km
                  · Speed: {telemetry.speed_kmh ?? "—"} km/h
                  <br />
                  GPS: {telemetry.lat ?? "—"},{" "}
                  {telemetry.lng ?? "—"}
                </div>
              )}

            </Card.Body>

          </Card>

        </Col>

      </Row>

    </div>
  );
}
