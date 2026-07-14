import { createHash, createHmac } from "node:crypto";
import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import { URL } from "node:url";

export interface ObjectStore {
  readBytes(objectKey: string): Promise<Buffer>;
}

export interface ObjectStoreConfig {
  endpoint: string;
  bucket: string;
  accessKey: string;
  secretKey: string;
  useSsl?: boolean;
  region?: string;
}

export function objectStoreFromEnv(env: Record<string, string | undefined> = process.env): ObjectStore | null {
  const endpoint = env.MIROFISH_OBJECT_STORAGE_ENDPOINT?.trim() ?? "";
  const bucket = env.MIROFISH_OBJECT_STORAGE_BUCKET?.trim() ?? "";
  const accessKey = env.MIROFISH_OBJECT_STORAGE_ACCESS_KEY?.trim() ?? "";
  const secretKey = env.MIROFISH_OBJECT_STORAGE_SECRET_KEY?.trim() ?? "";
  if (!endpoint || !bucket || !accessKey || !secretKey) {
    return null;
  }
  const useSsl = (env.MIROFISH_OBJECT_STORAGE_USE_SSL ?? "false").toLowerCase() === "true";
  return new S3CompatibleObjectStore({
    endpoint,
    bucket,
    accessKey,
    secretKey,
    useSsl,
    region: env.MIROFISH_OBJECT_STORAGE_REGION?.trim() || "us-east-1"
  });
}

export class S3CompatibleObjectStore implements ObjectStore {
  private readonly endpointUrl: string;
  private readonly bucket: string;
  private readonly accessKey: string;
  private readonly secretKey: string;
  private readonly region: string;

  constructor(config: ObjectStoreConfig) {
    const endpoint = config.endpoint.trim().replace(/\/+$/, "");
    if (!endpoint || !config.bucket.trim() || !config.accessKey.trim() || !config.secretKey.trim()) {
      throw new Error("object storage endpoint, bucket, access key, and secret are required");
    }
    this.endpointUrl = endpoint.startsWith("http://") || endpoint.startsWith("https://")
      ? endpoint
      : `${config.useSsl ? "https" : "http"}://${endpoint}`;
    this.bucket = config.bucket.trim();
    this.accessKey = config.accessKey.trim();
    this.secretKey = config.secretKey.trim();
    this.region = (config.region ?? "us-east-1").trim() || "us-east-1";
  }

  async readBytes(objectKey: string): Promise<Buffer> {
    const key = objectKey.trim().replace(/^\/+/, "");
    if (!key) {
      throw Object.assign(new Error("object_key is required"), { code: "VALIDATION_FAILED" });
    }
    const path = `/${encodeURIComponent(this.bucket).replace(/%2F/g, "/")}/${key.split("/").map(encodeURIComponent).join("/")}`;
    const url = new URL(path, this.endpointUrl);
    const now = new Date();
    const amzDate = formatAmzDate(now);
    const dateStamp = amzDate.slice(0, 8);
    const payloadHash = createHash("sha256").update("").digest("hex");
    const host = url.host;
    const canonicalHeaders = `host:${host}\nx-amz-content-sha256:${payloadHash}\nx-amz-date:${amzDate}\n`;
    const signedHeaders = "host;x-amz-content-sha256;x-amz-date";
    const canonicalRequest = [
      "GET",
      url.pathname,
      "",
      canonicalHeaders,
      signedHeaders,
      payloadHash
    ].join("\n");
    const credentialScope = `${dateStamp}/${this.region}/s3/aws4_request`;
    const stringToSign = [
      "AWS4-HMAC-SHA256",
      amzDate,
      credentialScope,
      createHash("sha256").update(canonicalRequest).digest("hex")
    ].join("\n");
    const signingKey = getSignatureKey(this.secretKey, dateStamp, this.region, "s3");
    const signature = createHmac("sha256", signingKey).update(stringToSign).digest("hex");
    const authorization = `AWS4-HMAC-SHA256 Credential=${this.accessKey}/${credentialScope}, SignedHeaders=${signedHeaders}, Signature=${signature}`;
    return await httpGet(url, {
      host,
      "x-amz-content-sha256": payloadHash,
      "x-amz-date": amzDate,
      authorization
    });
  }
}

function httpGet(url: URL, headers: Record<string, string>): Promise<Buffer> {
  const transport = url.protocol === "https:" ? httpsRequest : httpRequest;
  return new Promise((resolve, reject) => {
    const req = transport({
      protocol: url.protocol,
      hostname: url.hostname,
      port: url.port || undefined,
      path: `${url.pathname}${url.search}`,
      method: "GET",
      headers
    }, (res) => {
      const chunks: Buffer[] = [];
      res.on("data", (chunk) => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)));
      res.on("end", () => {
        const body = Buffer.concat(chunks);
        if ((res.statusCode ?? 500) >= 400) {
          reject(Object.assign(new Error(`object storage GET failed: ${res.statusCode}`), {
            code: "OBJECT_STORAGE_READ_FAILED",
            statusCode: res.statusCode,
            body: body.toString("utf8").slice(0, 500)
          }));
          return;
        }
        resolve(body);
      });
    });
    req.on("error", reject);
    req.end();
  });
}

function formatAmzDate(date: Date): string {
  const iso = date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  return iso;
}

function getSignatureKey(secretKey: string, dateStamp: string, region: string, service: string): Buffer {
  const kDate = createHmac("sha256", `AWS4${secretKey}`).update(dateStamp).digest();
  const kRegion = createHmac("sha256", kDate).update(region).digest();
  const kService = createHmac("sha256", kRegion).update(service).digest();
  return createHmac("sha256", kService).update("aws4_request").digest();
}
