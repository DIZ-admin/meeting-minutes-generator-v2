/**
 * File Uploader - Drag & Drop Component
 */
class FileUploader {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.options = { maxSize: 100 * 1024 * 1024, ...options };
        this.files = [];
        this.init();
    }

    init() {
        this.render();
        this.attachEvents();
    }

    render() {
        this.container.innerHTML = `
            <div class="file-uploader">
                <div class="drop-zone" id="dropZone">
                    <i class="fas fa-cloud-upload-alt"></i>
                    <h5>Drag files or <button type="button" id="selectBtn">choose</button></h5>
                    <small>MP3, WAV, M4A, JSON • Max 100MB</small>
                </div>
                <div class="file-list" id="fileList"></div>
                <input type="file" id="fileInput" multiple hidden>
            </div>
        `;
    }

    attachEvents() {
        const dropZone = this.container.querySelector('#dropZone');
        const fileInput = this.container.querySelector('#fileInput');
        const selectBtn = this.container.querySelector('#selectBtn');

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            this.handleFiles(e.dataTransfer.files);
        });

        selectBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => this.handleFiles(e.target.files));
    }

    handleFiles(fileList) {
        Array.from(fileList).forEach(file => {
            if (file.size <= this.options.maxSize) {
                this.files.push(file);
                this.addFileToList(file);
            }
        });
    }

    addFileToList(file) {
        const fileList = this.container.querySelector('#fileList');
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.innerHTML = `<span>${file.name}</span><button onclick="this.parentNode.remove()">×</button>`;
        fileList.appendChild(fileItem);
    }
}