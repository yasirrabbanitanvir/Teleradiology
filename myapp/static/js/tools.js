(function () {
        // ===== Globals (scoped inside IIFE to avoid leaking) =====
        let loaded = false;
        let series = []; // holds images loaded via file or URL
        let currentFrame = 0;
        let totalFrames = 0;
        let isPlaying = false;
        let playbackInterval = null;
        let playbackSpeed = 100; // ms
        let element = null; // cornerstone enabled element
        let activeTool = null;
        let dicomMetadata = {};
        let viewerInitialized = false;

        // Expose a couple that must be callable from HTML attributes
        window.openDicom = openDicom;
        window.backToFileList = backToFileList;

        // ===== Django helpers =====
        function getCookie(name) {
          const value = `; ${document.cookie}`.split(`; ${name}=`);
          if (value.length === 2) return value.pop().split(";").shift();
        }
        const csrftoken = getCookie("csrftoken");

        // Pre-configure WADO loader for same-origin auth/CSRF if needed
        cornerstoneWADOImageLoader.configure({
          beforeSend: function (xhr) {
            // Only attach on same-origin GETs
            try {
              const u = new URL(xhr.responseURL || "", window.location.href);
              if (u.origin === window.location.origin && csrftoken) {
                xhr.setRequestHeader("X-CSRFToken", csrftoken);
              }
            } catch (_) {}
          },
        });

        document.addEventListener("DOMContentLoaded", function () {
          // 1) Populate table from Django endpoint (GET /dicoms/ -> JSON [{id, file_url, uploaded_at}])
          fetch("/dicoms/")
            .then((r) => r.json())
            .then((data) => {
              const tbody = document.querySelector("#dicomTable tbody");
              tbody.innerHTML = "";
              data.forEach((item) => {
                const row = document.createElement("tr");
                row.innerHTML = `
                  <td>${item.id}</td>
                  <td>${item.file_url.split("/").pop()}</td>
                  <td>${item.uploaded_at}</td>
                  <td>
                    <button class="pacs-open-btn" data-url="${item.file_url}">
                      <i class="fas fa-eye"></i> Open Viewer
                    </button>
                  </td>`;
                row
                  .querySelector("button")
                  .addEventListener("click", () => openDicom(item.file_url));
                tbody.appendChild(row);
              });
            })
            .catch((err) => console.error("Failed to load /dicoms/ list", err));

          // 2) Initialize cornerstone only once, on page load
          initializeCornerstone();
          setupEventListeners();
          initializeTools();
          viewerInitialized = true;
          updateStatus("Ready to load DICOM files");
        });

        // ===== Core init =====
        function initializeCornerstone() {
          // Wire externals
          cornerstoneTools.external.Hammer = Hammer;
          cornerstoneTools.external.cornerstone = cornerstone;
          cornerstoneTools.external.cornerstoneMath = cornerstoneMath;
          cornerstoneWADOImageLoader.external.dicomParser = dicomParser;
          cornerstoneWADOImageLoader.external.cornerstone = cornerstone;

          // Tools init
          cornerstoneTools.init({
            showSVGCursors: true,
            mouseEnabled: true,
            touchEnabled: true,
          });

          element = document.getElementById("dicomImage");
          try {
            cornerstone.getEnabledElement(element);
          } catch (e) {
            cornerstone.enable(element);
          }
        }

        function setupEventListeners() {
          // File upload
          document
            .getElementById("uploadBtn")
            .addEventListener("click", () =>
              document.getElementById("dicomUpload").click()
            );
          document
            .getElementById("dicomUpload")
            .addEventListener("change", handleFileUpload);

          // Tool buttons
          document
            .getElementById("wwwcTool")
            .addEventListener("click", () => activateTool("Wwwc"));
          document
            .getElementById("zoomTool")
            .addEventListener("click", () => activateTool("Zoom"));
          document
            .getElementById("panTool")
            .addEventListener("click", () => activateTool("Pan"));
          document
            .getElementById("magnifyTool")
            .addEventListener("click", () => activateTool("Magnify"));
          document
            .getElementById("invertTool")
            .addEventListener("click", handleInvert);
          document
            .getElementById("resetTool")
            .addEventListener("click", handleReset);
          document
            .getElementById("eraserTool")
            .addEventListener("click", () => activateTool("Eraser"));

          // Annotation tools
          document
            .getElementById("lengthTool")
            .addEventListener("click", () => activateTool("Length"));
          document
            .getElementById("angleTool")
            .addEventListener("click", () => activateTool("Angle"));
          document
            .getElementById("probeTool")
            .addEventListener("click", () => activateTool("Probe"));
          document
            .getElementById("ellipticalRoiTool")
            .addEventListener("click", () => activateTool("EllipticalRoi"));
          document
            .getElementById("rectangleRoiTool")
            .addEventListener("click", () => activateTool("RectangleRoi"));
          document
            .getElementById("freehandRoiTool")
            .addEventListener("click", () => activateTool("FreehandRoi"));
          document
            .getElementById("arrowAnnotateTool")
            .addEventListener("click", () => activateTool("ArrowAnnotate"));
          document
            .getElementById("bidirectionalTool")
            .addEventListener("click", () => activateTool("Bidirectional"));

          // Dropdown
          document
            .getElementById("annotationTools")
            .addEventListener("click", () => {
              document
                .getElementById("annotationDropdown")
                .classList.toggle("show");
            });
          window.addEventListener("click", (ev) => {
            if (!ev.target.matches(".dropdown-toggle")) {
              const dd = document.getElementsByClassName("dropdown-content");
              for (let i = 0; i < dd.length; i++)
                dd[i].classList.remove("show");
            }
          });

          // Frames
          document
            .getElementById("frameSlider")
            .addEventListener("input", function () {
              if (loaded && totalFrames > 1) {
                currentFrame = parseInt(this.value, 10);
                loadFrame(currentFrame);
              }
            });

          // Cine
          document
            .getElementById("playClip")
            .addEventListener("click", togglePlayback);

          // Screenshot
          document
            .getElementById("captureBtn")
            .addEventListener("click", captureScreenshot);

          // Mouse wheel for frames
          element.addEventListener("wheel", handleMouseWheel, {
            passive: false,
          });

          // Resize
          window.addEventListener("resize", () => {
            if (loaded) cornerstone.resize(element, true);
          });
        }

        function initializeTools() {
          // Register tools (CornerstoneTools v4)
          cornerstoneTools.addTool(cornerstoneTools.WwwcTool);
          cornerstoneTools.addTool(cornerstoneTools.ZoomTool);
          cornerstoneTools.addTool(cornerstoneTools.PanTool);
          cornerstoneTools.addTool(cornerstoneTools.MagnifyTool);
          cornerstoneTools.addTool(cornerstoneTools.LengthTool);
          cornerstoneTools.addTool(cornerstoneTools.AngleTool);
          cornerstoneTools.addTool(cornerstoneTools.ProbeTool);
          cornerstoneTools.addTool(cornerstoneTools.EllipticalRoiTool);
          cornerstoneTools.addTool(cornerstoneTools.RectangleRoiTool);
          cornerstoneTools.addTool(cornerstoneTools.FreehandRoiTool);
          cornerstoneTools.addTool(cornerstoneTools.ArrowAnnotateTool);
          cornerstoneTools.addTool(cornerstoneTools.BidirectionalTool);
          cornerstoneTools.addTool(cornerstoneTools.EraserTool);
        }

        // ===== Table -> Viewer flow =====
        function openDicom(url) {
          // Hide table, show app
          document.querySelector(".dicom-table").style.display = "none";
          document.querySelector(".app-container").style.display = "block";

          // Track series from URL
          const imageId = "wadouri:" + url;
          series = [{ imageId, fileName: url.split("/").pop() || "Image" }];
          currentFrame = 0;

          // Ensure cornerstone is set up
          if (!viewerInitialized) {
            initializeCornerstone();
            setupEventListeners();
            initializeTools();
            viewerInitialized = true;
          }

          // Load first frame/image
          loadAndViewImage(series[0].imageId)
            .then(() => {
              updateSeriesList();
              activateTool("Wwwc");
              setTimeout(() => {
            if (element) {
          cornerstone.resize(element, true);
          cornerstone.fitToWindow(element); 
        }
      }, 100);
    })
            .catch((err) => {
              console.error("Error loading DICOM image", err);
              alert("Error loading DICOM image. Check console for details.");
            });
        }

        function backToFileList() {
          document.querySelector(".dicom-table").style.display = "block";
          document.querySelector(".app-container").style.display = "none";

          // Stop cine
          stopPlayback();
          document.getElementById("playClip").innerHTML =
            '<i class="fas fa-play"></i>';

          // Reset viewer surface, but keep cornerstone enabled
          try {
            cornerstone.reset(element);
          } catch (_) {}
          loaded = false;
          updateStatus("");
        }

        // ===== Loading helpers =====
        async function handleFileUpload(ev) {
          const files = ev.target.files;
          if (!files || !files.length) {
            updateStatus("No files selected");
            return;
          }
          updateStatus(`Loading ${files.length} file(s)...`);

          series = [];
          currentFrame = 0;
          for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const imageId =
              cornerstoneWADOImageLoader.wadouri.fileManager.add(file);
            series.push({ imageId, fileName: file.name });
          }

          if (series.length) {
            await loadAndViewImage(series[0].imageId);
            updateSeriesList();
            updateStatus("DICOM file(s) loaded successfully");
          }
        }

        async function loadAndViewImage(imageId) {
          updateStatus("Loading image...");
          const image = await cornerstone.loadImage(imageId);
          const defaultVp = cornerstone.getDefaultViewportForImage(
            element,
            image
          );
          if (image.windowWidth) defaultVp.voi.windowWidth = image.windowWidth;
          if (image.windowCenter)
            defaultVp.voi.windowCenter = image.windowCenter;

          cornerstone.displayImage(element, image, defaultVp);
          loaded = true;

          extractMetadata(image);

          totalFrames =
            parseInt(
              image.data &&
                image.data.intString &&
                image.data.intString("x00280008")
            ) || 1;
          if (totalFrames <= 0) totalFrames = 1;

          document.getElementById(
            "frameCount"
          ).textContent = `Total Frames: ${totalFrames}`;
          updateFrameInfo();

          if (totalFrames > 1) {
            populateFramesSidebar();
            setupFrameSlider();
          } else {
            document.getElementById("framesSidebar").style.display = "none";
            document.getElementById("frameSlider").parentElement.style.display =
              "none";
          }

          activateTool("Wwwc");

          element.removeEventListener(
            "cornerstoneimagerendered",
            onImageRendered
          );
          element.addEventListener("cornerstoneimagerendered", onImageRendered);
          updateStatus("Image loaded successfully");
          return image;
        }

        function extractMetadata(image) {
          if (!image || !image.data) return;
          const ds = image.data;
          const md = {};
          const common = [
            ["x00100010", "Patient Name"],
            ["x00100020", "Patient ID"],
            ["x00100030", "Patient Birth Date"],
            ["x00100040", "Patient Sex"],
            ["x00080020", "Study Date"],
            ["x00080030", "Study Time"],
            ["x00080060", "Modality"],
            ["x00080090", "Referring Physician"],
            ["x00081030", "Study Description"],
            ["x00181030", "Protocol Name"],
          ];
          common.forEach(([tag, name]) => {
            const v = ds.string(tag);
            if (v) md[name] = v;
          });
          md["Image Width"] = image.width;
          md["Image Height"] = image.height;
          md["Bits Allocated"] = ds.uint16("x00280100");
          md["Bits Stored"] = ds.uint16("x00280101");
          md["High Bit"] = ds.uint16("x00280102");
          md["Pixel Representation"] = ds.uint16("x00280103");
          md["Window Center"] = image.windowCenter;
          md["Window Width"] = image.windowWidth;
          dicomMetadata = md;
          displayMetadata();
        }

        function displayMetadata() {
          const container = document.getElementById("dicomMetadata");
          container.innerHTML = "";
          for (const [k, v] of Object.entries(dicomMetadata)) {
            const row = document.createElement("div");
            row.className = "metadata-row";
            row.innerHTML = `<span class="metadata-key">${k}:</span><span class="metadata-value">${
              v ?? ""
            }</span>`;
            container.appendChild(row);
          }
        }

        function updateSeriesList() {
          const container = document.getElementById("stackWrapper");
          container.innerHTML = "";
          series.forEach((item) => {
            const card = document.createElement("div");
            card.className = "series-thumbnail";
            card.innerHTML = `<div class="thumbnail-wrapper"></div><div class="thumbnail-label">${item.fileName}</div>`;
            const thumbEl = card.querySelector(".thumbnail-wrapper");
            try {
              cornerstone.getEnabledElement(thumbEl);
            } catch (_) {
              cornerstone.enable(thumbEl);
            }
            cornerstone
              .loadImage(item.imageId)
              .then((img) => {
                const vp = cornerstone.getDefaultViewportForImage(thumbEl, img);
                cornerstone.displayImage(thumbEl, img, vp);
                cornerstone.resize(thumbEl);
              })
              .catch((e) => {
                console.error("Thumb error", e);
                thumbEl.innerHTML = '<div class="error-thumbnail">Error</div>';
              });
            card.addEventListener("click", () =>
              loadAndViewImage(item.imageId)
            );
            container.appendChild(card);
          });
        }

        async function populateFramesSidebar() {
          const sidebar = document.getElementById("framesSidebar");
          sidebar.innerHTML = "";
          sidebar.style.display = "none"; // deliberately hidden;
          if (totalFrames <= 1) return;
          const baseImageId = series[0].imageId;
          for (let i = 0; i < totalFrames; i++) {
            const frameDiv = document.createElement("div");
            frameDiv.className = "frame-item";
            frameDiv.dataset.frameIndex = i;
            const canvas = document.createElement("canvas");
            try {
              cornerstone.enable(canvas);
              const img = await cornerstone.loadImage(
                `${baseImageId}?frame=${i}`
              );
              const vp = cornerstone.getDefaultViewportForImage(canvas, img);
              cornerstone.displayImage(canvas, img, vp);
              cornerstone.resize(canvas, true);
            } catch (err) {
              console.error(`Frame ${i} thumbnail error`, err);
              const ctx = canvas.getContext("2d");
              canvas.width = 100;
              canvas.height = 80;
              ctx.fillStyle = "#f44336";
              ctx.fillRect(0, 0, 100, 80);
              ctx.fillStyle = "#fff";
              ctx.font = "12px Arial";
              ctx.fillText(`Frame ${i + 1}`, 25, 45);
            }
            const label = document.createElement("span");
            label.textContent = `Frame ${i + 1}`;
            frameDiv.appendChild(canvas);
            frameDiv.appendChild(label);
            frameDiv.addEventListener("click", () => {
              currentFrame = i;
              loadFrame(currentFrame);
              updateFrameSlider();
            });
            sidebar.appendChild(frameDiv);
          }
        }

        function setupFrameSlider() {
          const slider = document.getElementById("frameSlider");
          slider.min = 0;
          slider.max = totalFrames - 1;
          slider.value = currentFrame;
          slider.parentElement.style.display =
            totalFrames > 1 ? "flex" : "none";
        }
        function updateFrameSlider() {
          document.getElementById("frameSlider").value = currentFrame;
        }

        async function loadFrame(frameIndex) {
          if (!loaded || frameIndex < 0 || frameIndex >= totalFrames) return;
          try {
            const image = await cornerstone.loadImage(
              `${series[0].imageId}?frame=${frameIndex}`
            );
            const vp = cornerstone.getViewport(element);
            cornerstone.displayImage(element, image, vp);
            currentFrame = frameIndex;
            updateFrameInfo();
            highlightCurrentFrameThumbnail();
          } catch (err) {
            console.error("Frame load error", err);
            updateStatus(`Error loading frame ${frameIndex + 1}`);
          }
        }

        function highlightCurrentFrameThumbnail() {
          document
            .querySelectorAll(".frame-item")
            .forEach((n) => n.classList.remove("active"));
          const cur = document.querySelector(
            `.frame-item[data-frame-index="${currentFrame}"]`
          );
          if (cur) cur.classList.add("active");
        }

        function updateFrameInfo() {
          document.getElementById("bottomleft").textContent = `Frame ${
            currentFrame + 1
          }/${totalFrames}`;
          document.getElementById("frameCounter").textContent = `Frame: ${
            currentFrame + 1
          }/${totalFrames}`;
        }

        // ===== Tools =====
        function activateTool(toolName) {
          deactivateAllTools();
          document
            .querySelectorAll(".toolButton")
            .forEach((btn) => btn.classList.remove("active"));
          const map = {
            Wwwc: "wwwcTool",
            Zoom: "zoomTool",
            Pan: "panTool",
            Magnify: "magnifyTool",
            Length: "lengthTool",
            Angle: "angleTool",
            Probe: "probeTool",
            EllipticalRoi: "ellipticalRoiTool",
            RectangleRoi: "rectangleRoiTool",
            FreehandRoi: "freehandRoiTool",
            ArrowAnnotate: "arrowAnnotateTool",
            Bidirectional: "bidirectionalTool",
            Eraser: "eraserTool",
          };
          if (map[toolName])
            document.getElementById(map[toolName]).classList.add("active");
          activeTool = toolName;
          cornerstoneTools.setToolActive(toolName, { mouseButtonMask: 1 });
          if (loaded) updateStatus(`${toolName} tool activated`);
        }

        function deactivateAllTools() {
          [
            "Wwwc",
            "Zoom",
            "Pan",
            "Magnify",
            "Length",
            "Angle",
            "Probe",
            "EllipticalRoi",
            "RectangleRoi",
            "FreehandRoi",
            "ArrowAnnotate",
            "Bidirectional",
            "Eraser",
          ].forEach((t) => {
            try {
              cornerstoneTools.setToolDisabled(t);
            } catch (_) {}
          });
        }

        function handleInvert() {
          if (!loaded) return;
          const vp = cornerstone.getViewport(element);
          vp.invert = !vp.invert;
          cornerstone.setViewport(element, vp);
          updateStatus("Image colors inverted");
        }
        function handleReset() {
          if (!loaded) return;
          cornerstone.reset(element);
          updateStatus("Image reset to default");
        }
        function handleMouseWheel(ev) {
          if (!loaded || totalFrames <= 1) return;
          ev.preventDefault();
          const delta = Math.max(-1, Math.min(1, ev.wheelDelta || -ev.detail));
          let nf = currentFrame - delta;
          nf = Math.max(0, Math.min(totalFrames - 1, nf));
          if (nf !== currentFrame) {
            currentFrame = nf;
            loadFrame(currentFrame);
            updateFrameSlider();
          }
        }

        function togglePlayback() {
          if (!loaded || totalFrames <= 1) {
            updateStatus("Playback not available - single frame image");
            return;
          }
          isPlaying = !isPlaying;
          const btn = document.getElementById("playClip");
          if (isPlaying) {
            btn.innerHTML = '<i class="fas fa-pause"></i>';
            startPlayback();
            updateStatus("Cine playback started");
          } else {
            btn.innerHTML = '<i class="fas fa-play"></i>';
            stopPlayback();
            updateStatus("Cine playback stopped");
          }
        }
        function startPlayback() {
          if (playbackInterval) clearInterval(playbackInterval);
          playbackInterval = setInterval(() => {
            currentFrame = (currentFrame + 1) % totalFrames;
            loadFrame(currentFrame);
            updateFrameSlider();
          }, playbackSpeed);
        }
        function stopPlayback() {
          if (playbackInterval) {
            clearInterval(playbackInterval);
            playbackInterval = null;
          }
        }

        function captureScreenshot() {
          if (!loaded) {
            updateStatus("No image loaded to capture");
            return;
          }
          const canvas = element.querySelector("canvas");
          if (!canvas) {
            updateStatus("Canvas not found");
            return;
          }
          const dataURL = canvas.toDataURL("image/png");
          const a = document.createElement("a");
          a.href = dataURL;
          a.download = `dicom-screenshot-${new Date()
            .toISOString()
            .slice(0, 19)}.png`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          updateStatus("Screenshot captured");
        }

        function onImageRendered() {
          const vp = cornerstone.getViewport(element);
          document.getElementById(
            "bottomright1"
          ).textContent = `WW/WC: ${Math.round(
            vp.voi.windowWidth
          )} / ${Math.round(vp.voi.windowCenter)}`;
          document.getElementById(
            "bottomright2"
          ).textContent = `Zoom: ${vp.scale.toFixed(2)}x`;
        }

        function updateStatus(msg) {
          const el = document.getElementById("statusMessage");
          el.textContent = msg;
          if (!msg) return;
          setTimeout(() => {
            if (el.textContent === msg) el.textContent = "";
          }, 5000);
        }

        // jQuery hook for calls openDicom
        $(".dicom-load-btn").on("click", function () {
          const fileUrl = $(this).data("file-url");
          if (fileUrl) openDicom(fileUrl);
        });
      })();

       // report.html
    //    document.getElementById('reportBtn').addEventListener('click', function() {
    //   window.open('/report/', '_blank'); 
    // });