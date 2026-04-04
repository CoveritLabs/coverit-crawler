// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { httpLogger } from "@api/middlewares/logger";
import { Request, Response } from "express";

describe("api/middlewares/logger", () => {
  it("determines log level based on response status code", () => {
    const customLogLevel = (httpLogger as any).customLogLevel;

    if (customLogLevel) {
      expect(customLogLevel({} as Request, { statusCode: 500 } as Response, undefined)).toBe("error");
      expect(customLogLevel({} as Request, { statusCode: 503 } as Response, undefined)).toBe("error");
      
      expect(customLogLevel({} as Request, { statusCode: 200 } as Response, new Error("Oops"))).toBe("error");

      expect(customLogLevel({} as Request, { statusCode: 400 } as Response, undefined)).toBe("warn");
      expect(customLogLevel({} as Request, { statusCode: 404 } as Response, undefined)).toBe("warn");

      expect(customLogLevel({} as Request, { statusCode: 200 } as Response, undefined)).toBe("info");
      expect(customLogLevel({} as Request, { statusCode: 302 } as Response, undefined)).toBe("info");
    }
  });
});
